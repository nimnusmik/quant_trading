# =============================================================================
# monitor/scheduler.py — APScheduler 기반 작업 스케줄러
#
# 스케줄:
#   매  1분  : 가격 3% 변동 감지 + TP/SL 청산 체크
#   매  5분  : 5분봉 S1~S6 신호 감지
#   매  1시간 : 1시간봉 S1~S6 신호 감지
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


def _job_price_check():
    """가격 변동 알림 + 포지션 TP/SL 체크."""
    check_price_alerts(send)

    # TP/SL 청산 체크 (오픈 포지션이 있을 때만)
    if trade_executor.get_position():
        for symbol, price in _last_prices.items():
            trade_executor.check_exit(price, bot_send=send)


def _job_signal_5m():
    """5분봉 신호 감지 및 자동매매 진입."""
    fired = check_signals(send, interval="5m")
    for symbol, strat_name, side in fired:
        price = _last_prices.get(symbol, 0)
        if price > 0:
            trade_executor.execute_signal(
                symbol=symbol,
                side=side,
                price=price,
                bot_send=send,
            )


def _job_signal_1h():
    """1시간봉 신호 감지 및 자동매매 진입."""
    fired = check_signals(send, interval="1h")
    for symbol, strat_name, side in fired:
        price = _last_prices.get(symbol, 0)
        if price > 0:
            trade_executor.execute_signal(
                symbol=symbol,
                side=side,
                price=price,
                bot_send=send,
            )


def _job_daily_briefing():
    """일일 브리핑 발송."""
    try:
        # 최신 가격으로 갱신
        prices = get_current_prices()
        _last_prices.update(prices)
    except Exception:
        pass
    msg = build_daily_briefing(_last_prices)
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
        _job_signal_5m,
        "interval",
        minutes=5,
        id="signal_5m",
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
