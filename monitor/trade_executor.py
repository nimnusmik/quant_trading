# =============================================================================
# monitor/trade_executor.py — Binance 자동매매 실행
#
# TRADE_MODE=paper  : 실제 주문 없이 로그만 기록 (기본값, 안전)
# TRADE_MODE=live   : 실제 시장가 주문 실행
#
# 안전 장치:
#   - 동시에 1개 포지션만 허용
#   - TP/SL 도달 시 자동 청산
#   - live 모드는 .env에서 TRADE_MODE=live로 명시적으로 변경해야 활성화
# =============================================================================

import os
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

# 현재 오픈 포지션 (메모리 내 단일 포지션 관리)
# {"symbol": str, "side": str, "entry_price": float, "tp": float, "sl": float, "size": float}
_open_position = None


def get_position() -> dict | None:
    """현재 오픈 포지션 반환. 없으면 None."""
    return _open_position


def execute_signal(
    symbol: str,
    side: str,
    price: float,
    tp_pct: float = 0.012,
    sl_pct: float = 0.005,
    size_usdt: float = 100.0,
    bot_send=None,
) -> dict:
    """
    신호에 따라 진입 주문을 실행합니다.

    Parameters
    ----------
    symbol    : "XRPUSDT" 등 Binance 심볼
    side      : "long" | "short"
    price     : 현재가 (시장가 주문이므로 참고용)
    tp_pct    : 익절 비율 (기본 1.2%)
    sl_pct    : 손절 비율 (기본 0.5%)
    size_usdt : 주문 금액 (USDT)
    bot_send  : 텔레그램 발송 함수 (선택)
    """
    global _open_position

    if _open_position is not None:
        print(f"[trade] 포지션 이미 있음 ({_open_position['symbol']} {_open_position['side']}) — 신규 진입 무시")
        return {}

    tp = price * (1 + tp_pct) if side == "long" else price * (1 - tp_pct)
    sl = price * (1 - sl_pct) if side == "long" else price * (1 + sl_pct)
    amount = size_usdt / price

    _open_position = {
        "symbol":      symbol,
        "side":        side,
        "entry_price": price,
        "tp":          tp,
        "sl":          sl,
        "size":        amount,
    }

    coin = symbol.replace("USDT", "")
    side_kr = "롱" if side == "long" else "숏"

    if _TRADE_MODE == "paper":
        msg = (
            f"📋 [PAPER] {side_kr} 진입\n"
            f"{coin} @ ${price:,.4f}\n"
            f"TP: ${tp:,.4f} (+{tp_pct*100:.1f}%) | SL: ${sl:,.4f} (-{sl_pct*100:.1f}%)\n"
            f"수량: {amount:.4f} {coin}"
        )
        print(msg)
        if bot_send:
            bot_send(msg)
        return _open_position

    # live 모드
    try:
        binance_side = "buy" if side == "long" else "sell"
        order = _exchange.create_market_order(symbol, binance_side, amount)
        filled_price = order.get("average", price)
        _open_position["entry_price"] = filled_price

        msg = (
            f"✅ [LIVE] {side_kr} 진입 완료\n"
            f"{coin} @ ${filled_price:,.4f}\n"
            f"TP: ${tp:,.4f} | SL: ${sl:,.4f}\n"
            f"주문ID: {order.get('id', 'N/A')}"
        )
        print(msg)
        if bot_send:
            bot_send(msg)
        return order

    except Exception as e:
        _open_position = None
        err = f"[trade] 주문 실패: {e}"
        print(err)
        if bot_send:
            bot_send(f"⚠️ 주문 실패: {e}")
        return {}


def check_exit(current_price: float, bot_send=None) -> str | None:
    """
    TP/SL 도달 여부를 확인하고 청산 처리합니다.
    price_monitor의 가격 업데이트마다 호출하세요.

    Returns
    -------
    str  청산 사유 ("TP 도달 +1.2%" 등) 또는 None
    """
    global _open_position
    if _open_position is None:
        return None

    p = _open_position
    reason = None

    if p["side"] == "long":
        if current_price >= p["tp"]:
            pnl_pct = (p["tp"] / p["entry_price"] - 1) * 100
            reason = f"TP 도달 +{pnl_pct:.2f}%"
        elif current_price <= p["sl"]:
            pnl_pct = (p["sl"] / p["entry_price"] - 1) * 100
            reason = f"SL 도달 {pnl_pct:.2f}%"
    else:  # short
        if current_price <= p["tp"]:
            pnl_pct = (p["entry_price"] / p["tp"] - 1) * 100
            reason = f"TP 도달 +{pnl_pct:.2f}%"
        elif current_price >= p["sl"]:
            pnl_pct = (p["entry_price"] / p["sl"] - 1) * 100
            reason = f"SL 도달 {pnl_pct:.2f}%"

    if reason:
        coin    = p["symbol"].replace("USDT", "")
        side_kr = "롱" if p["side"] == "long" else "숏"
        emoji   = "💰" if "TP" in reason else "🛑"
        msg = (
            f"{emoji} [{side_kr} 청산] {coin}\n"
            f"진입: ${p['entry_price']:,.4f} → 현재: ${current_price:,.4f}\n"
            f"결과: {reason}"
        )
        print(msg)
        if bot_send:
            bot_send(msg)
        _open_position = None

    return reason
