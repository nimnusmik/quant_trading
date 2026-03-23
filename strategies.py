# =============================================================================
# strategies.py — 6개 전략의 진입 신호 생성
#
# 스승의 노트:
#   각 전략은 "신호 생성기"입니다.
#   실제 매매 실행(포지션 관리, 손익 계산)은 backtest_engine.py가 담당합니다.
#   이 분리가 중요한 이유:
#     - 전략 로직을 바꿔도 엔진은 건드릴 필요가 없음
#     - 같은 엔진으로 전략들을 공정하게 비교 가능
#
#   각 전략 함수는 (long_entry, short_entry) 두 개의 boolean Series를 반환합니다.
#   True = "이 캔들에서 진입 신호 발생"
# =============================================================================

import pandas as pd
import numpy as np
from indicators import cross_above_level, cross_below_level


# ─────────────────────────────────────────────
# 전략1: EMA 크로스 + RSI + VWAP (추세추종 기본형)
# ─────────────────────────────────────────────

def strategy_ema_cross(df: pd.DataFrame,
                       rsi_long_max: float = 60.0,
                       rsi_short_min: float = 40.0,
                       vwap_tol: float = 0.005) -> tuple:
    """
    EMA 크로스가 발생하는 순간에만 진입합니다.

    롱 조건:
      ① 골든크로스 발생 (fast가 slow를 상향 돌파)
      ② RSI < rsi_long_max  (과열 구간에서 늦게 진입 방지)
      ③ 가격 > VWAP × (1 - vwap_tol)  (VWAP 근처 또는 위에 있을 것)
    """
    # ① EMA 크로스
    long_cross  = df["ema_cross_up"]
    short_cross = df["ema_cross_down"]

    # ② RSI 필터
    rsi_long_ok  = df["rsi"] < rsi_long_max
    rsi_short_ok = df["rsi"] > rsi_short_min

    # ③ VWAP 필터
    above_vwap = df["close"] > df["vwap"] * (1 - vwap_tol)
    below_vwap = df["close"] < df["vwap"] * (1 + vwap_tol)

    long_signal  = long_cross  & rsi_long_ok  & above_vwap
    short_signal = short_cross & rsi_short_ok & below_vwap

    return long_signal, short_signal


# ─────────────────────────────────────────────
# 전략2: VWAP 바운스 (평균회귀형)
# ─────────────────────────────────────────────

def strategy_vwap_bounce(df: pd.DataFrame,
                         rsi_long_min: float = 35.0,
                         rsi_long_max: float = 65.0,
                         rsi_short_min: float = 35.0,
                         rsi_short_max: float = 65.0,
                         vol_mult: float = 1.0) -> tuple:
    """
    가격이 VWAP을 돌파하는 순간에 진입합니다.
    VWAP = "당일 참가자 평균단가" 돌파 = 세력이 방향을 바꿈.

    롱 조건:
      ① 가격이 VWAP을 하→상 돌파 (cross_above)
      ② EMA9 상방 전환 중 (ema_fast 상승)
      ③ RSI가 과열 구간 아님 (35~65 사이)
      ④ 거래량이 평균 이상 (가짜 돌파 방지)
    """
    # ① VWAP 돌파 신호
    vwap_cross_up   = cross_above_level(df["close"] / df["vwap"], 1.0)
    vwap_cross_down = cross_below_level(df["close"] / df["vwap"], 1.0)

    # ② EMA 방향
    ema_rising  = df["ema_fast"] > df["ema_fast"].shift(1)
    ema_falling = df["ema_fast"] < df["ema_fast"].shift(1)

    # ③ RSI 범위
    rsi_long_ok  = (df["rsi"] >= rsi_long_min)  & (df["rsi"] <= rsi_long_max)
    rsi_short_ok = (df["rsi"] >= rsi_short_min) & (df["rsi"] <= rsi_short_max)

    # ④ 거래량 필터
    vol_ok = df["vol_ratio"] >= vol_mult

    long_signal  = vwap_cross_up   & ema_rising  & rsi_long_ok  & vol_ok
    short_signal = vwap_cross_down & ema_falling & rsi_short_ok & vol_ok

    return long_signal, short_signal


# ─────────────────────────────────────────────
# 전략3: RSI 극단 역추세 (핵심 전략)
# ─────────────────────────────────────────────

def strategy_rsi_extreme(df: pd.DataFrame,
                         rsi_oversold: float = 35.0,
                         rsi_overbought: float = 65.0,
                         vwap_tol: float = 0.005) -> tuple:
    """
    RSI가 극단에서 탈출하는 순간에만 진입합니다.
    30일 백테스트에서 승률 100%를 기록한 핵심 전략.

    롱 조건:
      ① RSI가 rsi_oversold 아래에서 → rsi_oversold 상향 돌파
      ② 가격이 VWAP의 ±vwap_tol 범위 내에 있을 것
      ③ EMA9 상승 중 (방향 전환 확인)

    스승의 노트:
      ①만으로는 "아직 더 빠질 수 있는" 상황에서 진입 위험.
      ②는 가격이 아직 "정상 범위"에 있는지 확인.
      ③은 실제 반등이 시작됐는지 확인.
      세 필터가 모두 충족될 때만 진입 = 신호가 드물지만 정확.
    """
    # ① RSI 극단 탈출
    rsi_escape_up   = cross_above_level(df["rsi"], rsi_oversold)   # 과매도 탈출
    rsi_escape_down = cross_below_level(df["rsi"], rsi_overbought)  # 과매수 탈출

    # ② VWAP 근접 확인
    near_vwap = df["price_vs_vwap"].abs() <= vwap_tol

    # ③ EMA 방향
    ema_rising  = df["ema_fast"] > df["ema_fast"].shift(1)
    ema_falling = df["ema_fast"] < df["ema_fast"].shift(1)

    long_signal  = rsi_escape_up   & near_vwap & ema_rising
    short_signal = rsi_escape_down & near_vwap & ema_falling

    return long_signal, short_signal


# ─────────────────────────────────────────────
# 전략4: 3중 EMA 정배열 + 눌림매수
# ─────────────────────────────────────────────

def strategy_triple_ema(df: pd.DataFrame,
                        rsi_reentry_long: float = 55.0,
                        rsi_reentry_short: float = 45.0) -> tuple:
    """
    EMA 3개가 정배열인 상태에서 RSI 눌림 후 재가속 순간에 진입합니다.
    "추세 확인 + 눌림 포착" = 고점 추격 방지.

    롱 조건:
      ① EMA 정배열 (fast > slow > trend)
      ② RSI가 rsi_reentry_long 아래에서 → 상향 돌파 (눌림 후 재가속)
      ③ 가격 > VWAP (상승 추세 확인)
    """
    # ① EMA 정배열 / 역배열
    bull_align = df["ema_bullish"]
    bear_align = df["ema_bearish"]

    # ② RSI 재가속
    rsi_reaccel_up   = cross_above_level(df["rsi"], rsi_reentry_long)
    rsi_reaccel_down = cross_below_level(df["rsi"], rsi_reentry_short)

    # ③ VWAP 위/아래
    above_vwap = df["price_vs_vwap"] > 0
    below_vwap = df["price_vs_vwap"] < 0

    long_signal  = bull_align & rsi_reaccel_up   & above_vwap
    short_signal = bear_align & rsi_reaccel_down & below_vwap

    return long_signal, short_signal


# ─────────────────────────────────────────────
# 전략5: 볼린저 밴드 스퀴즈 + VWAP
# ─────────────────────────────────────────────

def strategy_bb_squeeze(df: pd.DataFrame,
                        rsi_long_min: float = 40.0,
                        rsi_long_max: float = 60.0) -> tuple:
    """
    볼린저 밴드 수축(에너지 축적) 후 확장 시작 순간을 포착합니다.
    삼각수렴, 플래그 패턴의 수학적 표현.

    롱 조건:
      ① 직전 캔들이 스퀴즈 상태 (bb_squeeze = True)
      ② 현재 캔들에서 스퀴즈 해소 시작 (bb_squeeze = False로 전환)
      ③ 가격이 BB 중간선 위 + VWAP 위 (방향: 상방 폭발)
      ④ RSI가 과열 구간 아님
    """
    # ① ② 스퀴즈 해소 시점
    squeeze_break_up   = (df["bb_squeeze"].shift(1)) & (~df["bb_squeeze"])
    squeeze_break_down = (df["bb_squeeze"].shift(1)) & (~df["bb_squeeze"])

    # ③ 방향 확인
    above_mid  = df["close"] > df["bb_mid"]   # BB 중간선 위
    below_mid  = df["close"] < df["bb_mid"]
    above_vwap = df["price_vs_vwap"] > 0
    below_vwap = df["price_vs_vwap"] < 0

    # ④ RSI
    rsi_ok_long  = (df["rsi"] >= rsi_long_min) & (df["rsi"] <= rsi_long_max)
    rsi_ok_short = (df["rsi"] >= rsi_long_min) & (df["rsi"] <= rsi_long_max)

    long_signal  = squeeze_break_up   & above_mid & above_vwap & rsi_ok_long
    short_signal = squeeze_break_down & below_mid & below_vwap & rsi_ok_short

    return long_signal, short_signal


# ─────────────────────────────────────────────
# 전략6: MACD + VWAP + 거래량 (모멘텀 전환)
# ─────────────────────────────────────────────

def strategy_macd_volume(df: pd.DataFrame,
                         rsi_long_min: float = 35.0,
                         rsi_long_max: float = 65.0,
                         vol_mult: float = 1.2) -> tuple:
    """
    MACD 히스토그램이 음→양 전환하는 순간을 거래량으로 검증합니다.
    EMA 크로스보다 선행성이 좋지만 잡음도 많아서 거래량 필터가 핵심.

    롱 조건:
      ① MACD 히스토그램 음→양 전환 (0선 상향 돌파)
      ② 가격 > VWAP
      ③ RSI 중립 구간
      ④ 거래량 ≥ 평균 × vol_mult (거래량이 받쳐줘야 의미 있는 전환)
    """
    # ① MACD 히스토그램 전환
    hist_cross_up   = df["macd_cross_up"]
    hist_cross_down = df["macd_cross_down"]

    # ② VWAP 위/아래
    above_vwap = df["price_vs_vwap"] > 0
    below_vwap = df["price_vs_vwap"] < 0

    # ③ RSI 중립
    rsi_ok = (df["rsi"] >= rsi_long_min) & (df["rsi"] <= rsi_long_max)

    # ④ 거래량
    vol_ok = df["vol_ratio"] >= vol_mult

    long_signal  = hist_cross_up   & above_vwap & rsi_ok & vol_ok
    short_signal = hist_cross_down & below_vwap & rsi_ok & vol_ok

    return long_signal, short_signal


# ─────────────────────────────────────────────
# 전략 레지스트리 — 모든 전략을 딕셔너리로 관리
# ─────────────────────────────────────────────

STRATEGIES = {
    "S1_EMA_Cross":    strategy_ema_cross,
    "S2_VWAP_Bounce":  strategy_vwap_bounce,
    "S3_RSI_Extreme":  strategy_rsi_extreme,
    "S4_Triple_EMA":   strategy_triple_ema,
    "S5_BB_Squeeze":   strategy_bb_squeeze,
    "S6_MACD_Volume":  strategy_macd_volume,
}

# 전략 한글 이름 (차트/리포트용)
STRATEGY_LABELS = {
    "S1_EMA_Cross":    "EMA 크로스 추세추종",
    "S2_VWAP_Bounce":  "VWAP 바운스 평균회귀",
    "S3_RSI_Extreme":  "RSI 극단 역추세",
    "S4_Triple_EMA":   "3중 EMA 눌림매수",
    "S5_BB_Squeeze":   "볼린저 스퀴즈",
    "S6_MACD_Volume":  "MACD 모멘텀 전환",
}
