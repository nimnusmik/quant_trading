# =============================================================================
# monitor/signal_monitor.py — S1~S6 전략 실시간 신호 감지 (최적 파라미터 반영)
#
# 백테스트 결과 best_params_1h.csv의 최적 파라미터를 사용합니다.
# 통계적으로 유의한 전략(S1, S2, S6)만 활성화됩니다.
#
# 신호 판정 기준:
#   마지막으로 완성된 캔들(index -2)에서 신호 여부를 확인합니다.
#   index -1(현재 진행 중인 캔들)은 미완성이므로 제외합니다.
# =============================================================================

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import pandas as pd
from datetime import datetime

from indicators import compute_all
from strategies import STRATEGIES, STRATEGY_LABELS
from config import BINANCE_BASE_URL
from monitor.best_params import BEST_PARAMS, ACTIVE_STRATEGIES

WATCH_SYMBOLS = ["XRPUSDT"]
_KLINES_URL   = f"{BINANCE_BASE_URL}/api/v3/klines"

# 같은 (symbol, strategy, side) 조합의 중복 알림 방지 (캔들 단위)
_last_signal_candle = {}  # (symbol, strat, side, interval) -> datetime


def _fetch_latest_candles(symbol: str, interval: str, limit: int = 150) -> pd.DataFrame:
    """Binance에서 최근 캔들 데이터를 가져옵니다."""
    resp = requests.get(
        _KLINES_URL,
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()

    df = pd.DataFrame(resp.json(), columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "_ignore",
    ])
    df["datetime"] = (
        pd.to_datetime(df["open_time"], unit="ms", utc=True)
        .dt.tz_localize(None)
    )
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    return df[["datetime", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def _get_strategy_kwargs(strat_name: str, params: dict) -> dict:
    """전략 함수에 넘길 키워드 인자를 최적 파라미터에서 추출합니다."""
    kwargs = {}
    if strat_name == "S3_RSI_Extreme" and params.get("vwap_tol") is not None:
        kwargs["vwap_tol"] = params["vwap_tol"]
    return kwargs


def check_signals(bot_send, interval: str = "1h") -> list:
    """
    활성 전략 × 감시 심볼을 순회하여 최적 파라미터 기반으로 신호를 확인합니다.
    신호 발생 시 텔레그램 알림을 발송합니다.

    Returns
    -------
    list  발생한 신호 목록: [(symbol, strategy, side, params), ...]
    """
    fired = []

    # 전략별로 필요한 지표 파라미터가 다르므로 그룹핑
    # 같은 (ema_fast, ema_slow, rsi_period)를 공유하는 전략끼리 묶음
    param_groups = {}  # (ema_fast, ema_slow, rsi_period) -> [strat_name, ...]
    for strat_name in ACTIVE_STRATEGIES:
        if strat_name not in STRATEGIES:
            continue
        p = BEST_PARAMS.get(strat_name, {})
        key = (
            p.get("ema_fast", 9),
            p.get("ema_slow", 21),
            p.get("rsi_period", 14),
        )
        param_groups.setdefault(key, []).append(strat_name)

    for symbol in WATCH_SYMBOLS:
        try:
            raw_df = _fetch_latest_candles(symbol, interval)
        except Exception as e:
            print(f"[signal_monitor] {symbol} {interval} 데이터 오류: {e}")
            continue

        # 각 파라미터 그룹별로 지표 계산 → 신호 체크
        for (ema_fast, ema_slow, rsi_period), strat_names in param_groups.items():
            try:
                df = compute_all(
                    raw_df,
                    ema_fast=ema_fast,
                    ema_slow=ema_slow,
                    rsi_period=rsi_period,
                )
            except Exception as e:
                print(f"[signal_monitor] {symbol} 지표 계산 오류 (EMA {ema_fast}/{ema_slow}): {e}")
                continue

            last_candle = df.iloc[-2]
            last_candle_time = last_candle["datetime"]
            coin = symbol.replace("USDT", "")

            for strat_name in strat_names:
                strat_fn = STRATEGIES[strat_name]
                params = BEST_PARAMS.get(strat_name, {})
                kwargs = _get_strategy_kwargs(strat_name, params)

                try:
                    long_sig, short_sig = strat_fn(df, **kwargs)
                except Exception as e:
                    print(f"[signal_monitor] {strat_name} 신호 계산 오류: {e}")
                    continue

                for side, sig_series in [("long", long_sig)]:
                    if not sig_series.iloc[-2]:
                        continue

                    # 중복 알림 방지
                    key = (symbol, strat_name, side, interval)
                    if _last_signal_candle.get(key) == last_candle_time:
                        continue
                    _last_signal_candle[key] = last_candle_time

                    label = STRATEGY_LABELS[strat_name]
                    emoji = "🟢" if side == "long" else "🔴"
                    side_kr = "롱" if side == "long" else "숏"

                    price_vs_vwap_pct = last_candle.get("price_vs_vwap", 0) * 100

                    msg = (
                        f"{emoji} [{label}] {side_kr} 신호\n"
                        f"코인: {coin}/USDT | {interval}\n"
                        f"가격: ${last_candle['close']:,.4f}\n"
                        f"RSI: {last_candle['rsi']:.1f} | "
                        f"VWAP: ${last_candle['vwap']:,.4f} "
                        f"({price_vs_vwap_pct:+.2f}%)\n"
                        f"─────────────────\n"
                        f"EMA: {params.get('ema_fast', '?')}/{params.get('ema_slow', '?')} | "
                        f"TP: {params.get('tp_pct', 0):.1%} | "
                        f"SL: {params.get('sl_pct', 0):.1%}"
                    )
                    bot_send(msg)
                    fired.append((symbol, strat_name, side, params))

    return fired
