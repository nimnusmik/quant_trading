# =============================================================================
# monitor/price_monitor.py — XRP/BTC/ETH 가격 실시간 추적
#
# 동작 방식:
#   매 1분마다 Binance REST API로 현재가를 조회합니다.
#   직전 기록 대비 ±ALERT_THRESHOLD(기본 3%) 이상 변동 시 텔레그램 알림.
#   같은 코인은 30분(COOLDOWN_SECS) 내 중복 알림을 방지합니다.
# =============================================================================

import os
import time
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

WATCH_SYMBOLS = ["XRPUSDT"]
BRIEFING_SYMBOLS = ["XRPUSDT", "BTCUSDT", "ETHUSDT"]
_TICKER_URL   = "https://api.binance.com/api/v3/ticker/price"
COOLDOWN_SECS = 1800  # 30분

# 모듈 상태 (메모리 내 유지)
_last_prices      = {}  # symbol -> float
_last_alert_times = {}  # symbol -> timestamp (초)


def get_current_prices(symbols: list = None) -> dict:
    """Binance에서 심볼들의 현재가를 개별 조회합니다."""
    result = {}
    for symbol in (symbols or WATCH_SYMBOLS):
        resp = requests.get(_TICKER_URL, params={"symbol": symbol}, timeout=10)
        resp.raise_for_status()
        result[symbol] = float(resp.json()["price"])
    return result


def check_price_alerts(bot_send) -> None:
    """
    현재가를 조회하고 3% 이상 변동 시 텔레그램 알림을 발송합니다.
    스케줄러에서 매 1분마다 호출합니다.
    """
    threshold = float(os.getenv("ALERT_THRESHOLD", "0.03"))

    try:
        prices = get_current_prices()
    except Exception as e:
        print(f"[price_monitor] 가격 조회 실패: {e}")
        return

    now_ts = datetime.now(tz=timezone.utc).timestamp()

    for symbol, price in prices.items():
        # 첫 조회: 기준가만 저장, 알림 없음
        if symbol not in _last_prices:
            _last_prices[symbol] = price
            continue

        change = (price - _last_prices[symbol]) / _last_prices[symbol]
        last_alert_ts = _last_alert_times.get(symbol, 0)
        cooldown_ok   = (now_ts - last_alert_ts) > COOLDOWN_SECS

        if abs(change) >= threshold and cooldown_ok:
            coin      = symbol.replace("USDT", "")
            direction = "급등 🔺" if change > 0 else "급락 🔻"
            msg = (
                f"🚨 [{coin}] {direction} {change:+.2%}\n"
                f"현재가: ${price:,.4f}\n"
                f"기준가: ${_last_prices[symbol]:,.4f}"
            )
            bot_send(msg)
            _last_alert_times[symbol] = now_ts

        _last_prices[symbol] = price
