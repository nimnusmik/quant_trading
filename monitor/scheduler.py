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
from monitor import db
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
    for item in fired:
        # 5-element tuple: (symbol, strat_name, side, params, signal_id)
        # Backward-compatible with 4-element tuples
        if len(item) >= 5:
            symbol, strat_name, side, params, signal_id = item[:5]
        else:
            symbol, strat_name, side, params = item[:4]
            signal_id = None

        price = _last_prices.get(symbol, 0)
        if price <= 0:
            continue

        tp_pct = params.get("tp_pct", 0.012)
        sl_pct = params.get("sl_pct", 0.005)

        result = trade_executor.execute_signal(
            symbol=symbol,
            side=side,
            price=price,
            strategy=strat_name,
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            bot_send=send,
        )

        if result and signal_id is not None:
            try:
                db.update_signal_acted(signal_id)
            except Exception as e:
                print(f"[scheduler] DB signal_acted 업데이트 오류: {e}")


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


def startup_recovery(bot_send) -> None:
    """Load positions from DB and notify via Telegram."""
    trade_executor.load_positions_from_db()
    positions = trade_executor.get_all_positions()
    if positions:
        lines = []
        for strategy, p in positions.items():
            side_kr = "롱" if p["side"] == "long" else "숏"
            lines.append(
                f"  {strategy} {side_kr} @ ${p['entry_price']:,.4f}"
            )
        msg = (
            f"🔄 봇 재시작 — 포지션 {len(positions)}개 복구됨\n"
            + "\n".join(lines)
        )
    else:
        msg = "🔄 봇 재시작 — 오픈 포지션 없음"
    print(msg)
    bot_send(msg)


def create_scheduler() -> BackgroundScheduler:
    """스케줄러를 생성하고 모든 작업을 등록합니다."""
    # Initialize DB
    from monitor.db_migrate import migrate

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[scheduler] DATABASE_URL not set — DB persistence disabled")
    else:
        try:
            migrate(db_url)
            db.init_pool(db_url)
            startup_recovery(send)
        except Exception as e:
            print(f"[scheduler] DB 초기화 실패: {e}")
            print("[scheduler] DB persistence disabled — bot will run without persistence")
            send(f"⚠️ DB 연결 실패 — 포지션 저장 없이 실행됩니다: {e}")

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
