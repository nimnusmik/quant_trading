# =============================================================================
# backtest_engine.py — 백테스트 핵심 엔진
#
# 스승의 노트:
#   백테스트에서 가장 흔한 실수 세 가지:
#   1) 룩어헤드 바이어스 (Look-ahead Bias):
#      "이 캔들의 종가로 진입했는데, 해당 캔들의 고가까지 수익 계산"
#      실제로는 불가능. 반드시 "다음 캔들 시가"로 진입해야 합니다.
#   2) 생존자 편향: 현재 살아있는 코인만 테스트 (XRP는 해당 없음)
#   3) 수수료/슬리피지 미반영: 수익이 실제보다 과장됨
#
#   이 엔진은 1)을 해결하기 위해 "신호 발생 캔들 + 1"에 진입합니다.
# =============================================================================

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional

from config import INITIAL_CAPITAL, POSITION_SIZE, MAKER_FEE, SLIPPAGE


# ─────────────────────────────────────────────
# 거래 기록 구조체
# ─────────────────────────────────────────────

@dataclass
class Trade:
    """
    개별 거래 한 건의 모든 정보를 담는 구조체.
    dataclass를 쓰면 dict보다 타입 안전하고 가독성이 좋습니다.
    """
    trade_id:      int
    direction:     str        # "long" 또는 "short"
    entry_time:    pd.Timestamp
    entry_price:   float
    entry_bar:     int        # 진입 캔들 인덱스

    exit_time:     Optional[pd.Timestamp] = None
    exit_price:    Optional[float]        = None
    exit_bar:      Optional[int]          = None
    close_reason:  Optional[str]          = None  # "TP"/"SL"/"TIME"/"SIGNAL"/"FORCE"

    # 손익 계산 결과
    gross_pnl:  float = 0.0   # 수수료 전 손익 ($)
    fee:        float = 0.0   # 수수료 + 슬리피지 합계 ($)
    net_pnl:    float = 0.0   # 순손익 ($)
    pnl_pct:    float = 0.0   # 수익률 (%)
    hold_bars:  int   = 0     # 보유 기간 (캔들 수)


# ─────────────────────────────────────────────
# 백테스트 실행 함수
# ─────────────────────────────────────────────

def run_backtest(
    df: pd.DataFrame,
    long_signals:  pd.Series,
    short_signals: pd.Series,
    tp_pct:        float = 0.005,   # 익절 비율 (0.5%)
    sl_pct:        float = 0.010,   # 손절 비율 (1.0%)
    max_hold_bars: int   = 48,      # 최대 보유 캔들 수
    cooldown_bars: int   = 3,       # 청산 후 재진입 대기 캔들
    allow_short:   bool  = True,    # 숏 포지션 허용 여부
    fee:           float = MAKER_FEE,
    slippage:      float = SLIPPAGE,
) -> tuple:
    """
    백테스트를 실행하고 (거래 목록, 에퀴티 곡선) 을 반환합니다.

    Parameters
    ----------
    df            : 지표가 계산된 OHLCV DataFrame
    long_signals  : 롱 진입 신호 (bool Series)
    short_signals : 숏 진입 신호 (bool Series)
    tp_pct        : 익절 비율 (0.005 = 0.5%)
    sl_pct        : 손절 비율 (0.010 = 1.0%)
    max_hold_bars : 최대 보유 캔들 수
    cooldown_bars : 청산 후 재진입 금지 캔들 수
    allow_short   : False면 롱만 거래
    fee           : 편도 수수료 비율
    slippage      : 편도 슬리피지 비율

    Returns
    -------
    trades : list[Trade]        개별 거래 목록
    equity : list[float]        캔들별 자본금 추이
    """
    trades        = []
    trade_id      = 0
    capital       = INITIAL_CAPITAL

    # 현재 보유 포지션 (없으면 None)
    position: Optional[Trade] = None

    # 마지막 청산 시점 (쿨다운 적용용)
    last_exit_bar = -cooldown_bars - 1

    # 에퀴티 곡선: 각 캔들에서의 자본금 (미실현 손익 포함)
    equity_curve = []

    # ── 캔들 순회 ────────────────────────────────
    # 스승의 노트: iloc로 정수 인덱스 접근이 라벨(.loc) 접근보다 빠릅니다
    closes = df["close"].values
    highs  = df["high"].values
    lows   = df["low"].values
    times  = df["datetime"].values

    n = len(df)

    for i in range(1, n):  # 0번 캔들은 신호 발생 전이라 건너뜀
        price = closes[i]

        # ── 에퀴티 계산 (포지션 있으면 미실현 손익 반영) ──
        if position is not None:
            if position.direction == "long":
                unrealized = (price - position.entry_price) / position.entry_price
            else:
                unrealized = (position.entry_price - price) / position.entry_price
            current_equity = capital * (1 + unrealized * POSITION_SIZE)
        else:
            current_equity = capital
        equity_curve.append(current_equity)

        # ── 포지션 청산 판단 ─────────────────────────
        if position is not None:
            entry_price = position.entry_price
            hold_bars   = i - position.entry_bar

            if position.direction == "long":
                tp_price = entry_price * (1 + tp_pct)
                sl_price = entry_price * (1 - sl_pct)
            else:
                tp_price = entry_price * (1 - tp_pct)
                sl_price = entry_price * (1 + sl_pct)

            close_reason = None
            exit_price   = None

            # 익절/손절 판단: 캔들 내 고가/저가로 확인 (더 현실적)
            if position.direction == "long":
                if highs[i] >= tp_price:
                    # 스승의 노트: TP는 목표가에 지정가가 걸려있다고 가정
                    # 갭업으로 시가가 이미 TP를 넘었을 수도 있음
                    exit_price   = min(tp_price, highs[i])  # 현실적으로 처리
                    close_reason = "TP"
                elif lows[i] <= sl_price:
                    exit_price   = max(sl_price, lows[i])   # 슬리피지로 더 불리하게
                    close_reason = "SL"
            else:  # short
                if lows[i] <= tp_price:
                    exit_price   = max(tp_price, lows[i])
                    close_reason = "TP"
                elif highs[i] >= sl_price:
                    exit_price   = min(sl_price, highs[i])
                    close_reason = "SL"

            # 시간 초과 청산
            if close_reason is None and hold_bars >= max_hold_bars:
                exit_price   = price
                close_reason = "TIME"

            # 반대 신호 발생 시 청산
            if close_reason is None:
                if position.direction == "long"  and short_signals.iloc[i]:
                    exit_price   = price
                    close_reason = "SIGNAL"
                elif position.direction == "short" and long_signals.iloc[i]:
                    exit_price   = price
                    close_reason = "SIGNAL"

            # 청산 처리
            if close_reason is not None:
                _close_position(position, exit_price, i, times[i],
                                close_reason, fee, slippage, capital)

                capital          += position.net_pnl
                last_exit_bar     = i
                trades.append(position)
                position          = None

        # ── 진입 판단 (청산 직후 같은 캔들에서 재진입 없음) ──
        if position is None and (i - last_exit_bar) >= cooldown_bars:

            # 이전 캔들의 신호로 현재 캔들 시가에 진입 (룩어헤드 방지)
            # 여기서는 현재 캔들 종가로 근사 (시뮬레이션 단순화)
            if long_signals.iloc[i - 1] and capital > 0:
                entry_price = price * (1 + slippage)  # 슬리피지: 더 높은 가격에 체결
                position = Trade(
                    trade_id    = trade_id,
                    direction   = "long",
                    entry_time  = pd.Timestamp(times[i]),
                    entry_price = entry_price,
                    entry_bar   = i,
                )
                trade_id += 1

            elif allow_short and short_signals.iloc[i - 1] and capital > 0:
                entry_price = price * (1 - slippage)  # 숏: 더 낮은 가격에 체결
                position = Trade(
                    trade_id    = trade_id,
                    direction   = "short",
                    entry_time  = pd.Timestamp(times[i]),
                    entry_price = entry_price,
                    entry_bar   = i,
                )
                trade_id += 1

    # ── 백테스트 종료 시 미청산 포지션 강제 청산 ──
    if position is not None:
        final_price = closes[-1]
        _close_position(position, final_price, n - 1, times[-1],
                        "FORCE", fee, slippage, capital)
        capital += position.net_pnl
        trades.append(position)
        equity_curve[-1] = capital  # 마지막 에퀴티 수정

    return trades, equity_curve


def _close_position(trade: Trade, exit_price: float, exit_bar: int,
                    exit_time, reason: str, fee: float, slippage: float,
                    capital: float) -> None:
    """
    포지션을 청산하고 Trade 객체의 손익 필드를 채웁니다.
    (인플레이스 수정 — trade 객체를 직접 변경)
    """
    trade.exit_price  = exit_price
    trade.exit_bar    = exit_bar
    trade.exit_time   = pd.Timestamp(exit_time)
    trade.close_reason = reason
    trade.hold_bars   = exit_bar - trade.entry_bar

    notional = capital * POSITION_SIZE  # 투입 금액

    # 진입 슬리피지는 이미 entry_price에 반영됨 (lines 188, 199)
    # 청산 슬리피지는 여기서 exit_price에 반영
    if trade.direction == "long":
        adj_exit     = exit_price * (1 - slippage)   # 매도: 불리하게 낮은 가격에 체결
        price_change = (adj_exit - trade.entry_price) / trade.entry_price
    else:
        adj_exit     = exit_price * (1 + slippage)   # 숏 청산(매수): 불리하게 높은 가격에 체결
        price_change = (trade.entry_price - adj_exit) / trade.entry_price

    trade.gross_pnl = notional * price_change
    trade.fee       = notional * fee * 2              # 수수료만 왕복 (슬리피지는 가격에 반영)
    trade.net_pnl   = trade.gross_pnl - trade.fee
    trade.pnl_pct   = (trade.net_pnl / notional) * 100


# ─────────────────────────────────────────────
# 성과 지표 계산
# ─────────────────────────────────────────────

def compute_metrics(trades: list, equity_curve: list,
                    candles_per_day: int = 24) -> dict:
    """
    백테스트 결과에서 핵심 성과 지표를 계산합니다.

    Parameters
    ----------
    trades          : Trade 객체 목록
    equity_curve    : 캔들별 자본금 리스트
    candles_per_day : 연환산에 사용 (1h=24, 5m=288)
    """
    if not trades:
        return _empty_metrics()

    pnls     = [t.net_pnl  for t in trades]
    win_mask = [p > 0      for p in pnls]
    loss_mask = [p < 0     for p in pnls]

    total_trades = len(trades)
    wins         = sum(win_mask)
    losses       = sum(loss_mask)
    win_rate     = (wins / total_trades * 100) if total_trades > 0 else 0

    total_profit = sum(p for p in pnls if p > 0)
    total_loss   = abs(sum(p for p in pnls if p < 0))
    profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")

    total_net_pnl   = sum(pnls)
    total_return_pct = (total_net_pnl / INITIAL_CAPITAL) * 100

    avg_win  = (total_profit / wins)    if wins   > 0 else 0
    avg_loss = (total_loss   / losses)  if losses > 0 else 0
    rr_ratio = (avg_win / avg_loss)     if avg_loss > 0 else float("inf")

    total_fees = sum(t.fee for t in trades)
    avg_hold   = np.mean([t.hold_bars for t in trades])

    # ── MDD 계산 ──────────────────────────────────
    eq = np.array(equity_curve)
    peak = np.maximum.accumulate(eq)                     # 누적 최고점
    drawdown = (eq - peak) / peak                        # 낙폭 비율
    mdd = float(drawdown.min() * 100)                    # 최대 낙폭 (%)

    # ── Sharpe Ratio 계산 ─────────────────────────
    # 캔들별 수익률 → 연환산
    eq_series   = pd.Series(equity_curve)
    ret_series  = eq_series.pct_change().dropna()
    if ret_series.std() > 0:
        # 연간 캔들 수 = candles_per_day × 365
        annual_factor = np.sqrt(candles_per_day * 365)
        sharpe = float(ret_series.mean() / ret_series.std() * annual_factor)
    else:
        sharpe = 0.0

    # ── 월별 수익률 ───────────────────────────────
    monthly_pnl = {}
    for t in trades:
        if t.exit_time is not None:
            key = t.exit_time.strftime("%Y-%m")
            monthly_pnl[key] = monthly_pnl.get(key, 0) + t.net_pnl

    # 월별 수익률 (%)
    monthly_ret = {k: (v / INITIAL_CAPITAL * 100)
                   for k, v in sorted(monthly_pnl.items())}

    return {
        "total_trades":     total_trades,
        "win_rate":         round(win_rate, 1),
        "wins":             wins,
        "losses":           losses,
        "profit_factor":    round(profit_factor, 2),
        "total_return_pct": round(total_return_pct, 2),
        "total_net_pnl":    round(total_net_pnl, 2),
        "avg_win":          round(avg_win, 2),
        "avg_loss":         round(avg_loss, 2),
        "rr_ratio":         round(rr_ratio, 2),
        "mdd":              round(mdd, 2),
        "sharpe":           round(sharpe, 2),
        "total_fees":       round(total_fees, 2),
        "avg_hold_bars":    round(avg_hold, 1),
        "monthly_ret":      monthly_ret,
    }


def _empty_metrics() -> dict:
    """거래가 없을 때 반환하는 빈 지표."""
    return {
        "total_trades": 0, "win_rate": 0, "wins": 0, "losses": 0,
        "profit_factor": 0, "total_return_pct": 0, "total_net_pnl": 0,
        "avg_win": 0, "avg_loss": 0, "rr_ratio": 0,
        "mdd": 0, "sharpe": 0, "total_fees": 0, "avg_hold_bars": 0,
        "monthly_ret": {},
    }


def trades_to_dataframe(trades: list) -> pd.DataFrame:
    """
    Trade 목록을 pandas DataFrame으로 변환합니다.
    CSV 저장 및 분석에 사용합니다.
    """
    if not trades:
        return pd.DataFrame()

    rows = []
    for t in trades:
        rows.append({
            "trade_id":     t.trade_id,
            "direction":    t.direction,
            "entry_time":   t.entry_time,
            "entry_price":  t.entry_price,
            "exit_time":    t.exit_time,
            "exit_price":   t.exit_price,
            "close_reason": t.close_reason,
            "hold_bars":    t.hold_bars,
            "gross_pnl":    round(t.gross_pnl, 4),
            "fee":          round(t.fee, 4),
            "net_pnl":      round(t.net_pnl, 4),
            "pnl_pct":      round(t.pnl_pct, 4),
        })
    return pd.DataFrame(rows)
