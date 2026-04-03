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

try:
    from numba import njit
except ImportError:
    def njit(f=None, **kwargs):
        """numba 미설치 시 폴백: 데코레이터를 무시합니다."""
        if f is not None:
            return f
        return lambda fn: fn


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
# Numba JIT 컴파일 핵심 루프
# ─────────────────────────────────────────────

_CLOSE_REASONS = {0: "TP", 1: "SL", 2: "TIME", 3: "SIGNAL", 4: "FORCE"}


@njit(cache=True)
def _run_backtest_core(closes, opens, highs, lows, long_signals, short_signals,
                       tp_pct, sl_pct, max_hold_bars, cooldown_bars,
                       allow_short, fee, slippage,
                       initial_capital, position_size):
    """
    Numba JIT 컴파일된 백테스트 루프.
    진입: 다음 캔들 시가(open)로 체결 (실전과 동일)
    청산: 캔들 내 고가/저가로 TP/SL 판단, 종가로 시간초과/신호 청산
    """
    n = len(closes)
    equity_curve = np.empty(n - 1, dtype=np.float64)

    # 거래 기록 배열 사전 할당
    max_t = n // 2 + 1
    t_dir     = np.empty(max_t, dtype=np.int8)     # 1=long, -1=short
    t_e_bar   = np.empty(max_t, dtype=np.int64)
    t_e_price = np.empty(max_t, dtype=np.float64)
    t_x_bar   = np.empty(max_t, dtype=np.int64)
    t_x_price = np.empty(max_t, dtype=np.float64)
    t_reason  = np.empty(max_t, dtype=np.int8)     # 0=TP 1=SL 2=TIME 3=SIGNAL 4=FORCE
    t_gross   = np.empty(max_t, dtype=np.float64)
    t_fee     = np.empty(max_t, dtype=np.float64)
    t_net     = np.empty(max_t, dtype=np.float64)
    t_pct     = np.empty(max_t, dtype=np.float64)

    nt = 0                               # 거래 수
    capital = initial_capital
    in_pos = False
    pos_dir = 0                          # 1=long, -1=short
    pos_ep = 0.0                         # entry price
    pos_eb = 0                           # entry bar
    last_xb = -cooldown_bars - 1         # 마지막 청산 바

    for i in range(1, n):
        price = closes[i]
        open_price = opens[i]

        # ── 에퀴티 ──
        if in_pos:
            if pos_dir == 1:
                ur = (price - pos_ep) / pos_ep
            else:
                ur = (pos_ep - price) / pos_ep
            equity_curve[i - 1] = capital * (1.0 + ur * position_size)
        else:
            equity_curve[i - 1] = capital

        # ── 청산 판단 ──
        if in_pos:
            hb = i - pos_eb
            reason = -1
            xp = 0.0

            if pos_dir == 1:
                tp_p = pos_ep * (1.0 + tp_pct)
                sl_p = pos_ep * (1.0 - sl_pct)
                if highs[i] >= tp_p:
                    xp = min(tp_p, highs[i])
                    reason = 0
                elif lows[i] <= sl_p:
                    xp = max(sl_p, lows[i])
                    reason = 1
            else:
                tp_p = pos_ep * (1.0 - tp_pct)
                sl_p = pos_ep * (1.0 + sl_pct)
                if lows[i] <= tp_p:
                    xp = max(tp_p, lows[i])
                    reason = 0
                elif highs[i] >= sl_p:
                    xp = min(sl_p, highs[i])
                    reason = 1

            if reason == -1 and hb >= max_hold_bars:
                xp = price
                reason = 2

            if reason == -1:
                if pos_dir == 1 and short_signals[i]:
                    xp = price
                    reason = 3
                elif pos_dir == -1 and long_signals[i]:
                    xp = price
                    reason = 3

            if reason >= 0:
                notional = capital * position_size
                if pos_dir == 1:
                    pc = (xp * (1.0 - slippage) - pos_ep) / pos_ep
                else:
                    pc = (pos_ep - xp * (1.0 + slippage)) / pos_ep

                g = notional * pc
                f = notional * fee * 2.0
                n_pnl = g - f

                t_dir[nt]     = pos_dir
                t_e_bar[nt]   = pos_eb
                t_e_price[nt] = pos_ep
                t_x_bar[nt]   = i
                t_x_price[nt] = xp
                t_reason[nt]  = reason
                t_gross[nt]   = g
                t_fee[nt]     = f
                t_net[nt]     = n_pnl
                t_pct[nt]     = (n_pnl / notional) * 100.0
                nt += 1

                capital += n_pnl
                last_xb = i
                in_pos = False

        # ── 진입 판단 (시가로 체결) ──
        if not in_pos and (i - last_xb) >= cooldown_bars:
            if long_signals[i - 1] and capital > 0.0:
                pos_ep = open_price * (1.0 + slippage)
                pos_dir = 1
                pos_eb = i
                in_pos = True
            elif allow_short and short_signals[i - 1] and capital > 0.0:
                pos_ep = open_price * (1.0 - slippage)
                pos_dir = -1
                pos_eb = i
                in_pos = True

    # ── 미청산 포지션 강제 청산 ──
    if in_pos:
        fp = closes[n - 1]
        notional = capital * position_size
        if pos_dir == 1:
            pc = (fp * (1.0 - slippage) - pos_ep) / pos_ep
        else:
            pc = (pos_ep - fp * (1.0 + slippage)) / pos_ep

        g = notional * pc
        f = notional * fee * 2.0
        n_pnl = g - f

        t_dir[nt]     = pos_dir
        t_e_bar[nt]   = pos_eb
        t_e_price[nt] = pos_ep
        t_x_bar[nt]   = n - 1
        t_x_price[nt] = fp
        t_reason[nt]  = 4
        t_gross[nt]   = g
        t_fee[nt]     = f
        t_net[nt]     = n_pnl
        t_pct[nt]     = (n_pnl / notional) * 100.0
        nt += 1

        capital += n_pnl
        equity_curve[-1] = capital

    return (equity_curve, nt,
            t_dir[:nt], t_e_bar[:nt], t_e_price[:nt],
            t_x_bar[:nt], t_x_price[:nt], t_reason[:nt],
            t_gross[:nt], t_fee[:nt], t_net[:nt], t_pct[:nt])


# ─────────────────────────────────────────────
# 백테스트 실행 함수 (래퍼)
# ─────────────────────────────────────────────

def run_backtest(
    df: pd.DataFrame,
    long_signals:  pd.Series,
    short_signals: pd.Series,
    tp_pct:        float = 0.005,
    sl_pct:        float = 0.010,
    max_hold_bars: int   = 48,
    cooldown_bars: int   = 3,
    allow_short:   bool  = True,
    fee:           float = MAKER_FEE,
    slippage:      float = SLIPPAGE,
) -> tuple:
    """
    백테스트를 실행하고 (거래 목록, 에퀴티 곡선) 을 반환합니다.
    내부적으로 Numba JIT 컴파일된 코어 루프를 사용합니다.
    """
    closes = df["close"].values
    opens  = df["open"].values
    highs  = df["high"].values
    lows   = df["low"].values
    times  = df["datetime"].values
    long_arr  = long_signals.values.astype(np.bool_)
    short_arr = short_signals.values.astype(np.bool_)

    (equity, nt,
     dirs, e_bars, e_prices,
     x_bars, x_prices, reasons,
     gross, fees, nets, pcts) = _run_backtest_core(
        closes, opens, highs, lows, long_arr, short_arr,
        tp_pct, sl_pct, max_hold_bars, cooldown_bars,
        allow_short, fee, slippage,
        INITIAL_CAPITAL, POSITION_SIZE,
    )

    trades = []
    for i in range(nt):
        trades.append(Trade(
            trade_id     = i,
            direction    = "long" if dirs[i] == 1 else "short",
            entry_time   = pd.Timestamp(times[e_bars[i]]),
            entry_price  = float(e_prices[i]),
            entry_bar    = int(e_bars[i]),
            exit_time    = pd.Timestamp(times[x_bars[i]]),
            exit_price   = float(x_prices[i]),
            exit_bar     = int(x_bars[i]),
            close_reason = _CLOSE_REASONS[int(reasons[i])],
            gross_pnl    = float(gross[i]),
            fee          = float(fees[i]),
            net_pnl      = float(nets[i]),
            pnl_pct      = float(pcts[i]),
            hold_bars    = int(x_bars[i] - e_bars[i]),
        ))

    return trades, equity.tolist()


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
