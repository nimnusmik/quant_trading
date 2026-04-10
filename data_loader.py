# =============================================================================
# data_loader.py — Binance API로 OHLCV 데이터 수집
#
# 스승의 노트:
#   외부 API 호출 코드에서 가장 중요한 세 가지:
#   1) 재시도(Retry) 로직 — 네트워크는 언제든 끊깁니다
#   2) 캐싱 — 같은 데이터를 매번 API로 받으면 시간 낭비이자 Rate Limit 위험
#   3) 로그 — 어디서 실패했는지 알 수 없으면 디버깅 불가
#
#   Binance klines 엔드포인트:
#     GET /api/v3/klines
#     파라미터: symbol, interval, startTime(ms), endTime(ms), limit(max 1000)
#     응답: [[open_time, open, high, low, close, volume, close_time,
#              quote_volume, trades, ...], ...]
# =============================================================================

import os
import time
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from tqdm import tqdm

from config import (
    BINANCE_BASE_URL, SYMBOL,
    LOOKBACK_DAYS, TIMEFRAMES, API_LIMIT, API_SLEEP, DATA_DIR
)

_KLINES_URL = f"{BINANCE_BASE_URL}/api/v3/klines"


# ─────────────────────────────────────────────
# 내부 헬퍼: API 단일 요청
# ─────────────────────────────────────────────

def _fetch_chunk(interval: str, start_ms: int, end_ms: int,
                 limit: int = API_LIMIT, retries: int = 3) -> list:
    """
    Binance에서 kline 데이터 한 청크를 가져옵니다.

    Parameters
    ----------
    interval : str   Binance interval 문자열 ("1m", "5m", "1h" 등)
    start_ms : int   시작 시각 (Unix ms)
    end_ms   : int   종료 시각 (Unix ms)
    limit    : int   요청 캔들 수 (최대 1000)
    retries  : int   실패 시 재시도 횟수

    Returns
    -------
    list  각 원소는 Binance kline 배열
          [open_time, open, high, low, close, volume, close_time,
           quote_volume, trades, taker_buy_base, taker_buy_quote, ignore]
    """
    params = {
        "symbol":    SYMBOL,
        "interval":  interval,
        "startTime": start_ms,
        "endTime":   end_ms,
        "limit":     limit,
    }

    for attempt in range(retries):
        try:
            resp = requests.get(_KLINES_URL, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()

        except requests.RequestException as e:
            wait = 2 ** attempt  # 지수 백오프: 1초, 2초, 4초
            print(f"  [재시도 {attempt+1}/{retries}] {e} → {wait}초 대기")
            time.sleep(wait)

    raise RuntimeError(f"Binance API 호출 실패: {SYMBOL} {interval} start={start_ms}")


# ─────────────────────────────────────────────
# 공개 함수: 전체 기간 데이터 수집
# ─────────────────────────────────────────────

def fetch_ohlcv(timeframe_key: str, force_refresh: bool = False) -> pd.DataFrame:
    """
    지정한 타임프레임의 OHLCV 데이터를 반환합니다.
    로컬 캐시가 있으면 API 호출을 건너뜁니다.

    Parameters
    ----------
    timeframe_key  : str   config.TIMEFRAMES의 키 ("1h", "5m", "1m")
    force_refresh  : bool  True면 캐시 무시하고 API 재호출

    Returns
    -------
    pd.DataFrame  columns: [datetime, open, high, low, close, volume, quote_volume]
    """
    tf = TIMEFRAMES[timeframe_key]
    os.makedirs(DATA_DIR, exist_ok=True)

    # ── 캐시 파일 경로 ──────────────────────────────
    cache_path = os.path.join(DATA_DIR, f"xrp_{timeframe_key}_{LOOKBACK_DAYS}d.csv")

    if os.path.exists(cache_path) and not force_refresh:
        print(f"[캐시 로드] {cache_path}")
        df = pd.read_csv(cache_path, parse_dates=["datetime"])
        print(f"  → {len(df):,}개 캔들 | {df['datetime'].iloc[0]} ~ {df['datetime'].iloc[-1]}")
        return df

    # ── API에서 새로 수집 ───────────────────────────
    print(f"\n[Binance 수집] {tf['label']} | {LOOKBACK_DAYS}일치 {SYMBOL}")

    now_dt    = datetime.now(tz=timezone.utc)
    start_dt  = now_dt - timedelta(days=LOOKBACK_DAYS)
    start_ms  = int(start_dt.timestamp() * 1000)
    end_ms    = int(now_dt.timestamp() * 1000)
    interval  = tf["interval"]

    # 예상 총 요청 횟수 (진행 바용)
    interval_ms = _interval_to_ms(interval)
    total_candles  = (end_ms - start_ms) // interval_ms
    total_requests = (total_candles // API_LIMIT) + 2
    pbar = tqdm(total=total_requests, desc="API 요청")

    all_rows    = []
    current_ms  = start_ms

    while current_ms < end_ms:
        chunk = _fetch_chunk(interval, start_ms=current_ms, end_ms=end_ms)
        if not chunk:
            break

        all_rows.extend(chunk)
        pbar.update(1)

        # 마지막 캔들의 open_time + 1ms → 다음 청크 시작
        current_ms = chunk[-1][0] + 1

        # 청크가 limit보다 작으면 끝까지 받은 것
        if len(chunk) < API_LIMIT:
            break

        time.sleep(API_SLEEP)

    pbar.close()

    if not all_rows:
        raise RuntimeError(f"수집된 데이터 없음: {SYMBOL} {interval}")

    # ── 데이터프레임으로 변환 ───────────────────────
    # Binance kline 컬럼 순서:
    # 0:open_time  1:open  2:high  3:low  4:close  5:volume
    # 6:close_time 7:quote_volume  8:trades  9~11: taker 관련
    df_raw = pd.DataFrame(all_rows, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "_ignore",
    ])

    # open_time(ms) → datetime UTC
    df_raw["datetime"] = pd.to_datetime(df_raw["open_time"], unit="ms", utc=True)
    df_raw["datetime"] = df_raw["datetime"].dt.tz_localize(None)  # timezone 제거

    # 필요한 컬럼만 선택 + 타입 변환
    df_raw = df_raw[["datetime", "open", "high", "low", "close", "volume", "quote_volume"]].copy()
    for col in ["open", "high", "low", "close", "volume", "quote_volume"]:
        df_raw[col] = df_raw[col].astype(float)

    # 중복 제거 + 시간순 정렬
    df_raw = (df_raw
              .drop_duplicates(subset="datetime")
              .sort_values("datetime")
              .reset_index(drop=True))

    # ── 기간 필터 (최근 LOOKBACK_DAYS일만 유지) ─────
    cutoff = df_raw["datetime"].max() - pd.Timedelta(days=LOOKBACK_DAYS)
    df_raw = df_raw[df_raw["datetime"] >= cutoff].reset_index(drop=True)

    # 거래량 0인 캔들 제거
    df_raw = df_raw[df_raw["volume"] > 0].reset_index(drop=True)

    # ── 캐시 저장 ────────────────────────────────────
    df_raw.to_csv(cache_path, index=False)
    print(f"  → {len(df_raw):,}개 캔들 | {df_raw['datetime'].iloc[0]} ~ {df_raw['datetime'].iloc[-1]}")
    print(f"  → 캐시 저장: {cache_path}")

    return df_raw


# ─────────────────────────────────────────────
# 데이터 품질 검사
# ─────────────────────────────────────────────

def validate_data(df: pd.DataFrame, timeframe_key: str) -> bool:
    """
    수집된 데이터의 기본 품질을 검사합니다.
    문제가 있으면 경고를 출력하지만 프로세스는 계속합니다.
    """
    issues = []

    # NaN 검사
    nan_count = df.isnull().sum().sum()
    if nan_count > 0:
        issues.append(f"NaN {nan_count}개 발견")

    # 가격 논리 검사
    invalid_hl = (df["high"] < df["low"]).sum()
    if invalid_hl > 0:
        issues.append(f"고가 < 저가 행 {invalid_hl}개")

    # 시간 간격 검사 (예상 간격의 3배 초과 갭 탐지)
    gap_map = {
        "1h":  pd.Timedelta(hours=1),
        "30m": pd.Timedelta(minutes=30),
        "5m":  pd.Timedelta(minutes=5),
        "1m":  pd.Timedelta(minutes=1),
    }
    expected_gap = gap_map.get(timeframe_key, pd.Timedelta(minutes=5))
    time_diffs   = df["datetime"].diff().dropna()
    large_gaps   = (time_diffs > expected_gap * 3).sum()
    if large_gaps > 0:
        issues.append(f"시간 갭 {large_gaps}개 (예상의 3배 초과) — 거래소 점검 또는 데이터 누락")

    if issues:
        print(f"\n[데이터 품질 경고]")
        for i in issues:
            print(f"  ⚠ {i}")
    else:
        print(f"  ✓ 데이터 품질 이상 없음 ({len(df):,}개 캔들)")

    return len(issues) == 0


# ─────────────────────────────────────────────
# 내부 유틸: interval 문자열 → 밀리초
# ─────────────────────────────────────────────

def _interval_to_ms(interval: str) -> int:
    """
    Binance interval 문자열을 밀리초로 변환합니다.
    예: "1m" → 60_000, "5m" → 300_000, "1h" → 3_600_000
    """
    unit   = interval[-1]
    amount = int(interval[:-1])
    multipliers = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    return amount * multipliers[unit]
