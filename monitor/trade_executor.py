# =============================================================================
# monitor/trade_executor.py — Binance 자동매매 실행 (전략별 독립 포지션)
#
# TRADE_MODE=paper  : 실제 주문 없이 로그만 기록 (기본값, 안전)
# TRADE_MODE=live   : 실제 시장가 주문 실행
#
# 안전 장치:
#   - 전략별로 독립 포지션 관리 (최대 활성 전략 수만큼 동시 보유 가능)
#   - 같은 전략은 동시에 1개 포지션만 허용
#   - TP/SL 도달 시 자동 청산
#   - live 모드는 .env에서 TRADE_MODE=live로 명시적으로 변경해야 활성화
# =============================================================================

import logging
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

_TRADE_MODE = os.getenv("TRADE_MODE", "paper").lower()

# live 모드일 때만 ccxt 초기화
_exchange = None
if _TRADE_MODE == "live":
    try:
        import ccxt
        _exchange = ccxt.binance({
            "apiKey": os.getenv("BINANCE_API_KEY", ""),
            "secret": os.getenv("BINANCE_SECRET", ""),
        })
    except ImportError:
        print("[trade_executor] ccxt 미설치 — pip install ccxt")

logger = logging.getLogger(__name__)

# 전략별 오픈 포지션 관리
# {"S1_EMA_Cross": {"symbol": str, "side": str, "entry_price": float, "tp": float, "sl": float, "size": float}, ...}
_open_positions = {}


def _persist_position(position: dict) -> None:
    """Persist a position to the DB. Logs warning on failure."""
    try:
        from monitor import db
        db.insert_position(position)
    except Exception as e:
        logger.warning("[trade_executor] DB persist position failed: %s", e)


def _persist_close(strategy: str, position: dict, exit_price: float, reason: str) -> None:
    """Delete position from DB and insert into trade_history. Logs warning on failure."""
    try:
        from monitor import db
        db.delete_position(strategy)

        pnl_pct = _calc_pnl_pct(position, exit_price)
        trade = {
            "strategy": strategy,
            "symbol": position["symbol"],
            "side": position["side"],
            "entry_price": position["entry_price"],
            "exit_price": exit_price,
            "size": position["size"],
            "pnl_pct": round(pnl_pct, 4),
            "exit_reason": reason[:20] if reason else None,
            "opened_at": position.get("opened_at", datetime.now(timezone.utc)),
        }
        db.insert_trade(trade)
    except Exception as e:
        logger.warning("[trade_executor] DB persist close failed: %s", e)


def _calc_pnl_pct(position: dict, exit_price: float) -> float:
    """Calculate PnL percentage using actual exit price."""
    if position["side"] == "long":
        return (exit_price / position["entry_price"] - 1) * 100
    else:
        return (position["entry_price"] / exit_price - 1) * 100


def load_positions_from_db() -> None:
    """Load all open positions from DB into the in-memory dict. For restart recovery."""
    try:
        from monitor import db
        rows = db.get_open_positions()
        for row in rows:
            strategy = row["strategy"]
            _open_positions[strategy] = {
                "symbol": row["symbol"],
                "side": row["side"],
                "entry_price": float(row["entry_price"]),
                "tp": float(row["tp"]),
                "sl": float(row["sl"]),
                "size": float(row["size"]),
                "strategy": strategy,
                "opened_at": row.get("opened_at"),
            }
        logger.info("[trade_executor] Loaded %d positions from DB", len(rows))
    except Exception as e:
        logger.warning("[trade_executor] Failed to load positions from DB: %s", e)


def get_position(strategy: str = None) -> dict | None:
    """전략별 오픈 포지션 반환. strategy=None이면 전체 딕셔너리."""
    if strategy is None:
        return _open_positions if _open_positions else None
    return _open_positions.get(strategy)


def get_all_positions() -> dict:
    """모든 오픈 포지션 반환."""
    return dict(_open_positions)


def execute_signal(
    symbol: str,
    side: str,
    price: float,
    strategy: str = "unknown",
    tp_pct: float = 0.012,
    sl_pct: float = 0.005,
    size_usdt: float = 100.0,
    bot_send=None,
) -> dict:
    """
    신호에 따라 진입 주문을 실행합니다. 전략별 독립 포지션.

    Parameters
    ----------
    symbol    : "XRPUSDT" 등 Binance 심볼
    side      : "long" | "short"
    price     : 현재가 (시장가 주문이므로 참고용)
    strategy  : 전략 이름 (예: "S1_EMA_Cross")
    tp_pct    : 익절 비율
    sl_pct    : 손절 비율
    size_usdt : 주문 금액 (USDT)
    bot_send  : 텔레그램 발송 함수 (선택)
    """
    if strategy in _open_positions:
        print(f"[trade] {strategy} 포지션 이미 있음 — 신규 진입 무시")
        return {}

    tp = price * (1 + tp_pct) if side == "long" else price * (1 - tp_pct)
    sl = price * (1 - sl_pct) if side == "long" else price * (1 + sl_pct)
    amount = size_usdt / price

    position = {
        "symbol":      symbol,
        "side":        side,
        "entry_price": price,
        "tp":          tp,
        "sl":          sl,
        "size":        amount,
        "strategy":    strategy,
    }

    coin = symbol.replace("USDT", "")
    side_kr = "롱" if side == "long" else "숏"
    n_active = len(_open_positions) + 1

    if _TRADE_MODE == "paper":
        _open_positions[strategy] = position
        _persist_position(position)
        msg = (
            f"📋 [PAPER] {side_kr} 진입 — {strategy}\n"
            f"{coin} @ ${price:,.4f}\n"
            f"TP: ${tp:,.4f} (+{tp_pct*100:.1f}%) | SL: ${sl:,.4f} (-{sl_pct*100:.1f}%)\n"
            f"수량: {amount:.4f} {coin}\n"
            f"활성 포지션: {n_active}개"
        )
        print(msg)
        if bot_send:
            bot_send(msg)
        return position

    # live 모드
    try:
        binance_side = "buy" if side == "long" else "sell"
        order = _exchange.create_market_order(symbol, binance_side, amount)
        filled_price = order.get("average", price)
        position["entry_price"] = filled_price
        _open_positions[strategy] = position
        _persist_position(position)

        msg = (
            f"✅ [LIVE] {side_kr} 진입 완료 — {strategy}\n"
            f"{coin} @ ${filled_price:,.4f}\n"
            f"TP: ${tp:,.4f} | SL: ${sl:,.4f}\n"
            f"주문ID: {order.get('id', 'N/A')}\n"
            f"활성 포지션: {n_active}개"
        )
        print(msg)
        if bot_send:
            bot_send(msg)
        return order

    except Exception as e:
        err = f"[trade] {strategy} 주문 실패: {e}"
        print(err)
        if bot_send:
            bot_send(f"⚠️ {strategy} 주문 실패: {e}")
        return {}


def check_exit(current_price: float, bot_send=None) -> list:
    """
    모든 오픈 포지션의 TP/SL 도달 여부를 확인하고 청산 처리합니다.

    Returns
    -------
    list  청산된 전략 목록: [("S1_EMA_Cross", "TP 도달 +1.2%"), ...]
    """
    closed = []
    to_close = []  # list of (strategy, position_copy, exit_price, reason)

    for strategy, p in _open_positions.items():
        reason = None

        if p["side"] == "long":
            if current_price >= p["tp"]:
                pnl_pct = _calc_pnl_pct(p, current_price)
                reason = f"TP 도달 +{pnl_pct:.2f}%"
            elif current_price <= p["sl"]:
                pnl_pct = _calc_pnl_pct(p, current_price)
                reason = f"SL 도달 {pnl_pct:.2f}%"
        else:  # short
            if current_price <= p["tp"]:
                pnl_pct = _calc_pnl_pct(p, current_price)
                reason = f"TP 도달 +{pnl_pct:.2f}%"
            elif current_price >= p["sl"]:
                pnl_pct = _calc_pnl_pct(p, current_price)
                reason = f"SL 도달 {pnl_pct:.2f}%"

        if reason:
            coin    = p["symbol"].replace("USDT", "")
            side_kr = "롱" if p["side"] == "long" else "숏"
            emoji   = "💰" if "TP" in reason else "🛑"
            msg = (
                f"{emoji} [{side_kr} 청산] {coin} — {strategy}\n"
                f"진입: ${p['entry_price']:,.4f} → 현재: ${current_price:,.4f}\n"
                f"결과: {reason}"
            )
            print(msg)
            if bot_send:
                bot_send(msg)
            to_close.append((strategy, dict(p), current_price, reason))
            closed.append((strategy, reason))

    for strategy, position, exit_price, reason in to_close:
        del _open_positions[strategy]
        _persist_close(strategy, position, exit_price, reason)

    return closed
