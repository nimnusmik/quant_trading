# =============================================================================
# indicators.py — 기술적 지표 계산
#
# 스승의 노트:
#   지표 계산은 반드시 pandas/numpy 벡터 연산으로 구현하세요.
#   for 루프로 캔들 하나씩 계산하면 4000개 캔들에도 수십 초가 걸립니다.
#   벡터 연산은 같은 작업을 0.01초 이내에 처리합니다.
#
#   또한 지표는 "순수 함수"로 만드세요.
#   입력 DataFrame을 수정하지 않고 새 Series/DataFrame을 반환합니다.
#   이렇게 해야 여러 전략에서 같은 데이터를 공유할 때 충돌이 없습니다.
# =============================================================================

import pandas as pd
import numpy as np


# ─────────────────────────────────────────────
# EMA (지수이동평균)
# ─────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    """
    지수이동평균 (Exponential Moving Average).
    단순이동평균(SMA)보다 최근 데이터에 더 큰 가중치를 부여합니다.

    adjust=False: 재귀 공식 사용 (실제 트레이딩 플랫폼과 동일한 방식)
    """
    return series.ewm(span=period, adjust=False).mean()


# ─────────────────────────────────────────────
# RSI (상대강도지수)
# ─────────────────────────────────────────────

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI (Relative Strength Index).
    0~100 사이 값. 70 이상 = 과매수, 30 이하 = 과매도.

    Wilder 방식(ewm alpha=1/period)으로 계산합니다.
    많은 차트 플랫폼의 기본값과 동일합니다.
    """
    delta = series.diff()                          # 전일 대비 변화량

    gain = delta.clip(lower=0)                     # 상승분만 남기기 (하락은 0으로)
    loss = (-delta).clip(lower=0)                  # 하락분만 남기기 (상승은 0으로)

    # Wilder 평활화: alpha = 1/period (ewm com 방식으로 변환: com = period-1)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()

    # RS = 평균상승 / 평균하락, 0으로 나누기 방지
    rs = avg_gain / avg_loss.replace(0, np.nan)

    return 100 - (100 / (1 + rs))


# ─────────────────────────────────────────────
# VWAP (거래량 가중 평균 가격)
# ─────────────────────────────────────────────

def vwap(df: pd.DataFrame, reset_daily: bool = True) -> pd.Series:
    """
    VWAP (Volume-Weighted Average Price).
    기관 트레이더들이 "공정 가치"로 참고하는 핵심 지표.

    Parameters
    ----------
    df           : OHLCV DataFrame (datetime, high, low, close, volume 필요)
    reset_daily  : True면 매일 00:00 UTC에 VWAP을 리셋 (일반적인 사용법)

    Returns
    -------
    pd.Series  각 캔들의 VWAP 값
    """
    # 전형적 가격(Typical Price) = (고가 + 저가 + 종가) / 3
    typical_price = (df["high"] + df["low"] + df["close"]) / 3

    # 거래량 가중 가격
    tp_vol = typical_price * df["volume"]

    if reset_daily:
        # 날짜별 그룹화 후 누적합 계산
        date_group = df["datetime"].dt.date

        # 그룹별 누적합 → 그룹별 VWAP
        cumtp  = tp_vol.groupby(date_group).cumsum()
        cumvol = df["volume"].groupby(date_group).cumsum()
    else:
        cumtp  = tp_vol.cumsum()
        cumvol = df["volume"].cumsum()

    # 0 거래량 보호 (NaN 방지)
    return cumtp / cumvol.replace(0, np.nan)


# ─────────────────────────────────────────────
# 볼린저 밴드
# ─────────────────────────────────────────────

def bollinger_bands(series: pd.Series, period: int = 20,
                    std_mult: float = 2.0) -> pd.DataFrame:
    """
    볼린저 밴드 (Bollinger Bands).

    Returns
    -------
    DataFrame with columns: [bb_mid, bb_upper, bb_lower, bb_width, bb_pct]
      bb_mid   : 중간선 (SMA)
      bb_upper : 상단선
      bb_lower : 하단선
      bb_width : 밴드 폭 (상단-하단) — 스퀴즈 감지에 사용
      bb_pct   : %B (현재 가격이 밴드 내 어디에 있는지 0~1)
    """
    mid   = series.rolling(period).mean()
    std   = series.rolling(period).std()
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    width = upper - lower
    pct   = (series - lower) / width.replace(0, np.nan)

    return pd.DataFrame({
        "bb_mid":   mid,
        "bb_upper": upper,
        "bb_lower": lower,
        "bb_width": width,
        "bb_pct":   pct,
    })


# ─────────────────────────────────────────────
# MACD
# ─────────────────────────────────────────────

def macd(series: pd.Series,
         fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    MACD (Moving Average Convergence Divergence).

    Returns
    -------
    DataFrame with columns: [macd_line, macd_signal, macd_hist]
      macd_line   : 빠른 EMA - 느린 EMA
      macd_signal : macd_line의 9기간 EMA (시그널선)
      macd_hist   : macd_line - macd_signal (히스토그램)
    """
    ema_fast    = ema(series, fast)
    ema_slow    = ema(series, slow)
    macd_line   = ema_fast - ema_slow
    macd_signal = ema(macd_line, signal)
    macd_hist   = macd_line - macd_signal

    return pd.DataFrame({
        "macd_line":   macd_line,
        "macd_signal": macd_signal,
        "macd_hist":   macd_hist,
    })


# ─────────────────────────────────────────────
# 거래량 이동평균
# ─────────────────────────────────────────────

def volume_ma(series: pd.Series, period: int = 20) -> pd.Series:
    """
    거래량의 단순이동평균.
    현재 거래량이 평균의 몇 배인지 판단하는 기준선으로 사용합니다.
    """
    return series.rolling(period).mean()


# ─────────────────────────────────────────────
# 크로스 감지 유틸리티
# ─────────────────────────────────────────────

def crossover(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """
    fast가 slow를 아래→위로 돌파(골든크로스)하는 캔들을 True로 표시.

    전봉: fast < slow  (아래에 있었고)
    현봉: fast > slow  (위로 올라감)
    """
    prev_below = fast.shift(1) < slow.shift(1)  # 직전에 아래
    curr_above = fast > slow                     # 현재 위
    return prev_below & curr_above


def crossunder(fast: pd.Series, slow: pd.Series) -> pd.Series:
    """
    fast가 slow를 위→아래로 이탈(데드크로스)하는 캔들을 True로 표시.
    """
    prev_above = fast.shift(1) > slow.shift(1)  # 직전에 위
    curr_below = fast < slow                     # 현재 아래
    return prev_above & curr_below


def cross_above_level(series: pd.Series, level: float) -> pd.Series:
    """
    series가 특정 수평선(level)을 아래→위로 돌파하는 순간을 True로 표시.
    예: RSI가 30을 상향 돌파 → 과매도 탈출 신호
    """
    return (series.shift(1) < level) & (series >= level)


def cross_below_level(series: pd.Series, level: float) -> pd.Series:
    """
    series가 특정 수평선(level)을 위→아래로 이탈하는 순간을 True로 표시.
    예: RSI가 70을 하향 이탈 → 과매수 탈출 신호
    """
    return (series.shift(1) > level) & (series <= level)


# ─────────────────────────────────────────────
# 전체 지표 일괄 계산
# ─────────────────────────────────────────────

def compute_all(df: pd.DataFrame,
                ema_fast: int = 9, ema_slow: int = 21,
                ema_trend: int = 50,
                rsi_period: int = 7) -> pd.DataFrame:
    """
    6개 전략에서 공통으로 필요한 지표를 한 번에 계산합니다.
    DataFrame에 컬럼을 추가해서 반환합니다.

    스승의 노트:
      이렇게 "한 번에 계산"하면 6개 전략이 동일한 지표를 공유합니다.
      각 전략에서 따로 계산하면 미세한 부동소수점 차이로
      전략 간 비교가 왜곡될 수 있습니다.
    """
    result = df.copy()

    # ── EMA ──────────────────────────────────────
    result["ema_fast"]  = ema(result["close"], ema_fast)
    result["ema_slow"]  = ema(result["close"], ema_slow)
    result["ema_trend"] = ema(result["close"], ema_trend)  # 장기 추세선

    # ── RSI ──────────────────────────────────────
    result["rsi"] = rsi(result["close"], rsi_period)

    # ── VWAP ─────────────────────────────────────
    result["vwap"] = vwap(result)

    # ── 볼린저 밴드 ──────────────────────────────
    bb = bollinger_bands(result["close"])
    for col in bb.columns:
        result[col] = bb[col]

    # ── MACD ─────────────────────────────────────
    mc = macd(result["close"])
    for col in mc.columns:
        result[col] = mc[col]

    # ── 거래량 이동평균 ──────────────────────────
    result["vol_ma20"] = volume_ma(result["volume"], 20)

    # ── 파생 지표 ────────────────────────────────
    # EMA 정배열 여부: 빠른선 > 느린선 > 장기선
    result["ema_bullish"] = (
        (result["ema_fast"] > result["ema_slow"]) &
        (result["ema_slow"] > result["ema_trend"])
    )
    result["ema_bearish"] = (
        (result["ema_fast"] < result["ema_slow"]) &
        (result["ema_slow"] < result["ema_trend"])
    )

    # VWAP 대비 가격 위치 (양수 = 위, 음수 = 아래)
    result["price_vs_vwap"] = (result["close"] - result["vwap"]) / result["vwap"]

    # 거래량 배수 (현재 거래량 / 20봉 평균)
    result["vol_ratio"] = result["volume"] / result["vol_ma20"].replace(0, np.nan)

    # 볼린저 스퀴즈: 밴드 폭이 20봉 평균 대비 80% 이하
    result["bb_squeeze"] = result["bb_width"] < result["bb_width"].rolling(20).mean() * 0.8

    # EMA 크로스 신호
    result["ema_cross_up"]   = crossover(result["ema_fast"], result["ema_slow"])
    result["ema_cross_down"] = crossunder(result["ema_fast"], result["ema_slow"])

    # MACD 히스토그램 방향 전환
    result["macd_cross_up"]   = crossover(result["macd_hist"],
                                           pd.Series(0, index=result.index))
    result["macd_cross_down"] = crossunder(result["macd_hist"],
                                            pd.Series(0, index=result.index))

    return result
