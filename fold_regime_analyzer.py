# =============================================================================
# fold_regime_analyzer.py — 폴드별 시장 조건 분석
#
# 각 폴드의 검증 기간 동안 시장이 어떤 상태였는지 분석하고,
# 전략 성과와의 상관관계를 찾아 "언제 전략을 켜고 끌지" 규칙을 도출합니다.
# =============================================================================

import numpy as np
import pandas as pd

from data_loader import fetch_ohlcv
from config import TIMEFRAMES, WF_TRAIN_DAYS, WF_TEST_DAYS


# ─────────────────────────────────────────────
# ADX (Average Directional Index) 계산
# ─────────────────────────────────────────────

def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    ADX: 추세의 강도를 0~100으로 나타냅니다.
    25 이상이면 추세가 있고, 이하면 횡보장.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # True Range
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # +DM / -DM
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # Smoothed (Wilder 방식)
    atr = pd.Series(tr, index=df.index).ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean() / atr

    # DX → ADX
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()

    return adx


def compute_atr_pct(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR을 가격 대비 %로 계산 (변동성 지표)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    return atr / close * 100


# ─────────────────────────────────────────────
# 폴드별 시장 분석
# ─────────────────────────────────────────────

def analyze_folds(timeframe_key: str = "1h",
                  fold_metrics: dict = None,
                  strategy_key: str = None) -> pd.DataFrame:
    """
    각 폴드의 검증 기간 동안 시장 조건을 분석합니다.

    Returns
    -------
    DataFrame: 폴드별 시장 지표 + 전략 성과
    """
    tf = TIMEFRAMES[timeframe_key]
    candles_per_day = tf["candles_per_day"]

    df = fetch_ohlcv(timeframe_key)

    # ADX, ATR, EMA 계산
    df["adx"] = compute_adx(df)
    df["atr_pct"] = compute_atr_pct(df)
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema50_slope"] = (df["ema50"] - df["ema50"].shift(candles_per_day)) / df["ema50"].shift(candles_per_day) * 100

    # Walk-Forward 분할 재현
    train_candles = WF_TRAIN_DAYS * candles_per_day
    test_candles = WF_TEST_DAYS * candles_per_day
    n = len(df)

    folds = []
    fold_i = 0
    start = 0

    while start + train_candles + test_candles <= n:
        test_start = start + train_candles
        test_end = test_start + test_candles

        df_test = df.iloc[test_start:test_end]

        # 시장 지표 (검증 기간 평균)
        date_start = df_test["datetime"].iloc[0]
        date_end = df_test["datetime"].iloc[-1]
        xrp_start = df_test["close"].iloc[0]
        xrp_end = df_test["close"].iloc[-1]
        xrp_ret = (xrp_end - xrp_start) / xrp_start * 100

        avg_adx = df_test["adx"].mean()
        avg_atr = df_test["atr_pct"].mean()
        ema_slope = df_test["ema50_slope"].mean()

        fold_data = {
            "fold": fold_i + 1,
            "period": f"{date_start.strftime('%y.%m')}~{date_end.strftime('%y.%m')}",
            "xrp_ret": round(xrp_ret, 1),
            "adx": round(avg_adx, 1),
            "ema_slope": round(ema_slope, 2),
            "atr_pct": round(avg_atr, 2),
        }

        # 전략 성과 매칭
        if fold_metrics and strategy_key and strategy_key in fold_metrics:
            fm_list = fold_metrics[strategy_key]
            if fold_i < len(fm_list):
                fm = fm_list[fold_i]
                fold_data["strat_ret"] = round(fm["total_return_pct"], 1)
                fold_data["trades"] = fm["total_trades"]
                fold_data["win_rate"] = round(fm["win_rate"], 0)
                fold_data["result"] = "WIN" if fm["total_return_pct"] > 0 else "LOSS"

        folds.append(fold_data)
        start += test_candles
        fold_i += 1

    return pd.DataFrame(folds)


def print_regime_analysis(df_folds: pd.DataFrame, strategy_key: str):
    """폴드별 시장 분석 결과를 출력합니다."""
    print(f"\n{'='*90}")
    print(f"  폴드별 시장 조건 분석 — {strategy_key}")
    print(f"{'='*90}")
    print(f"  ADX: 추세 강도 (25↑=추세, 25↓=횡보)")
    print(f"  EMA기울기: 50시간 이동평균의 방향 (+상승, -하락)")
    print(f"  ATR: 변동성 (높을수록 크게 움직임)")
    print()

    # 테이블 헤더
    has_strat = "strat_ret" in df_folds.columns
    header = f"  {'폴드':<5} {'기간':<14} {'XRP수익률':>9} {'ADX':>6} {'EMA기울기':>9} {'변동성':>7}"
    if has_strat:
        header += f" {'전략수익률':>10} {'거래수':>6} {'판정':>6}"
    print(header)
    print(f"  {'-'*85}")

    for _, row in df_folds.iterrows():
        line = (f"  F{int(row['fold']):<4} {row['period']:<14} "
                f"{row['xrp_ret']:>+8.1f}% {row['adx']:>5.1f} "
                f"{row['ema_slope']:>+8.2f}% {row['atr_pct']:>6.2f}%")
        if has_strat:
            line += (f" {row['strat_ret']:>+9.1f}% {int(row['trades']):>5}건"
                     f"  {row['result']}")
        print(line)

    if not has_strat:
        return

    # WIN / LOSS 그룹 비교
    wins = df_folds[df_folds["result"] == "WIN"]
    losses = df_folds[df_folds["result"] == "LOSS"]

    print(f"\n  {'─'*50}")
    print(f"  WIN  그룹 ({len(wins)}개 폴드):  "
          f"평균 ADX {wins['adx'].mean():.1f}  "
          f"EMA기울기 {wins['ema_slope'].mean():+.2f}%  "
          f"변동성 {wins['atr_pct'].mean():.2f}%  "
          f"전략수익 {wins['strat_ret'].mean():+.1f}%")
    print(f"  LOSS 그룹 ({len(losses)}개 폴드):  "
          f"평균 ADX {losses['adx'].mean():.1f}  "
          f"EMA기울기 {losses['ema_slope'].mean():+.2f}%  "
          f"변동성 {losses['atr_pct'].mean():.2f}%  "
          f"전략수익 {losses['strat_ret'].mean():+.1f}%")

    # 규칙 도출
    adx_threshold = round((wins["adx"].mean() + losses["adx"].mean()) / 2, 0)
    slope_threshold = 0  # 방향 기준

    # 규칙 적용 시뮬레이션
    df_folds["pass_filter"] = (
        (df_folds["adx"] >= adx_threshold) &
        (df_folds["ema_slope"] > slope_threshold)
    )

    filtered = df_folds[df_folds["pass_filter"]]
    blocked = df_folds[~df_folds["pass_filter"]]

    print(f"\n  {'─'*50}")
    print(f"  도출 규칙: ADX >= {adx_threshold:.0f} AND EMA기울기 > 0")
    print(f"  {'─'*50}")
    print(f"  통과 폴드 ({len(filtered)}개): 평균 수익률 {filtered['strat_ret'].mean():+.1f}%")
    if len(blocked) > 0:
        print(f"  차단 폴드 ({len(blocked)}개): 평균 수익률 {blocked['strat_ret'].mean():+.1f}% ← 이 손실을 회피")
    print(f"  필터 적용 시 합산: {filtered['strat_ret'].sum():+.1f}% (전체 {df_folds['strat_ret'].sum():+.1f}%)")


# ─────────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # 독립 실행 시: 2년 백테스트 결과 없이도 시장 분석만 가능
    df_folds = analyze_folds("1h")
    print_regime_analysis(df_folds, "시장 조건만 분석")
