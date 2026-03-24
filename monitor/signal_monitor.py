# =============================================================================
# monitor/signal_monitor.py — S1~S6 전략 실시간 신호 감지
#
# 기존 indicators.py / strategies.py를 그대로 재사용합니다.
# 5분봉은 매 5분, 1시간봉은 매 1시간 스케줄로 호출됩니다.
#
# 신호 판정 기준:
#   마지막으로 완성된 캔들(index -2)에서 신호 여부를 확인합니다.
#   index -1(현재 진행 중인 캔들)은 미완성이므로 제외합니다.
# =============================================================================

import sys
import os

# monitor/ 하위에서 프로젝트 루트의 모듈을 임포트하기 위한 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import pandas as pd
from datetime import datetime

from indicators import compute_all
from strategies import STRATEGIES, STRATEGY_LABELS
from config import BINANCE_BASE_URL

WATCH_SYMBOLS = ["XRPUSDT", "BTCUSDT", "ETHUSDT"]
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


def check_signals(bot_send, interval: str = "1h") -> list:
    """
    모든 감시 심볼 × S1~S6 전략을 순회하여 신호를 확인합니다.
    신호 발생 시 텔레그램 알림을 발송합니다.

    Returns
    -------
    list  발생한 신호 목록: [(symbol, strategy, side), ...]
    """
    fired = []

    for symbol in WATCH_SYMBOLS:
        try:
            df = _fetch_latest_candles(symbol, interval)
            df = compute_all(df)
        except Exception as e:
            print(f"[signal_monitor] {symbol} {interval} 데이터 오류: {e}")
            continue

        # 마지막 완성 캔들
        last_candle = df.iloc[-2]
        last_candle_time = last_candle["datetime"]
        coin = symbol.replace("USDT", "")

        for strat_name, strat_fn in STRATEGIES.items():
            try:
                long_sig, short_sig = strat_fn(df)
            except Exception as e:
                print(f"[signal_monitor] {strat_name} 신호 계산 오류: {e}")
                continue

            for side, sig_series in [("long", long_sig), ("short", short_sig)]:
                if not sig_series.iloc[-2]:
                    continue

                # 중복 알림 방지: 같은 캔들에서 이미 발송한 신호 무시
                key = (symbol, strat_name, side, interval)
                if _last_signal_candle.get(key) == last_candle_time:
                    continue
                _last_signal_candle[key] = last_candle_time

                # 메시지 포맷
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
                    f"({price_vs_vwap_pct:+.2f}%)"
                )
                bot_send(msg)
                fired.append((symbol, strat_name, side))

    return fired
