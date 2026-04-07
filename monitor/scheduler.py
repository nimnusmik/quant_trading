# =============================================================================
# monitor/scheduler.py — APScheduler 기반 작업 스케줄러
#
# 스케줄:
#   매  1분  : 가격 3% 변동 감지 + TP/SL 청산 체크
#   매  5분  : 5분봉 신호 감지 (활성 전략만, 최적 파라미터)
#   매  1시간 : 1시간봉 신호 감지 (활성 전략만, 최적 파라미터)
#   매일 09:00 KST : 일일 브리핑 발송
# =============================================================================

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from monitor.telegram_bot import send
from monitor.price_monitor import check_price_alerts, get_current_prices, _last_prices
from monitor.signal_monitor import check_signals
from monitor.news_monitor import build_daily_briefing
from monitor import trade_executor
from monitor.best_params import BEST_PARAMS, ACTIVE_STRATEGIES


def _job_price_check():
    """가격 변동 알림 + 포지션 TP/SL 체크."""
    check_price_alerts(send)

    # TP/SL 청산 체크 (오픈 포지션이 있을 때만)
    positions = trade_executor.get_all_positions()
    if positions:
        for strategy, pos in list(positions.items()):
            price = _last_prices.get(pos["symbol"], 0)
            if price > 0:
                trade_executor.check_exit(price, bot_send=send)


def _execute_signals(fired: list):
    """신호 발생 시 최적 파라미터의 TP/SL로 진입합니다."""
    for symbol, strat_name, side, params in fired:
        price = _last_prices.get(symbol, 0)
        if price <= 0:
            continue

        tp_pct = params.get("tp_pct", 0.012)
        sl_pct = params.get("sl_pct", 0.005)

        trade_executor.execute_signal(
            symbol=symbol,
            side=side,
            price=price,
            strategy=strat_name,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            bot_send=send,
        )


def _job_signal_5m():
    """5분봉 신호 감지 및 자동매매 진입."""
    fired = check_signals(send, interval="5m")
    _execute_signals(fired)


def _job_signal_1h():
    """1시간봉 신호 감지 및 자동매매 진입."""
    fired = check_signals(send, interval="1h")
    _execute_signals(fired)


def _job_daily_briefing():
    """일일 브리핑 발송."""
    from monitor.price_monitor import BRIEFING_SYMBOLS
    try:
        prices = get_current_prices(BRIEFING_SYMBOLS)
        _last_prices.update(prices)
    except Exception:
        pass
    msg = build_daily_briefing(prices)
    send(msg)


def create_scheduler() -> BackgroundScheduler:
    """스케줄러를 생성하고 모든 작업을 등록합니다."""
    scheduler = BackgroundScheduler(timezone="Asia/Seoul")

    scheduler.add_job(
        _job_price_check,
        "interval",
        minutes=1,
        id="price_check",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _job_signal_1h,
        "interval",
        hours=1,
        id="signal_1h",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _job_daily_briefing,
        CronTrigger(hour=9, minute=0, timezone="Asia/Seoul"),
        id="daily_briefing",
        max_instances=1,
    )

    return scheduler
