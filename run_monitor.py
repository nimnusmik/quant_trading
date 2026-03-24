#!/usr/bin/env python3
# =============================================================================
# run_monitor.py — 실시간 모니터링 봇 진입점
#
# 사용법:
#   python run_monitor.py                   # 정상 실행 (스케줄러 시작)
#   python run_monitor.py --dry-run         # 텔레그램 연결 테스트만
#   python run_monitor.py --briefing-now    # 일일 브리핑 즉시 발송
#   python run_monitor.py --signal-now 1h  # 1시간봉 신호 즉시 체크
#   python run_monitor.py --signal-now 5m  # 5분봉 신호 즉시 체크
#
# 사전 준비:
#   1. pip install -r requirements_monitor.txt
#   2. cp .env.example .env  →  .env에 실제 키 입력
# =============================================================================

import argparse
import time
import sys
import os
from dotenv import load_dotenv

load_dotenv()

# 프로젝트 루트를 경로에 추가 (monitor/ 내 모듈들이 indicators 등 임포트 가능하게)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _check_env():
    """필수 환경변수 점검."""
    missing = []
    for key in ["TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]:
        if not os.getenv(key):
            missing.append(key)
    if missing:
        print(f"[오류] .env에 다음 항목이 없습니다: {', '.join(missing)}")
        print("  .env.example 파일을 참고해 .env를 설정하세요.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="XRP 실시간 모니터링 + 자동매매 + 일일 브리핑 봇"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="텔레그램 연결 테스트 메시지만 발송하고 종료",
    )
    parser.add_argument(
        "--briefing-now",
        action="store_true",
        help="일일 브리핑을 지금 즉시 발송하고 종료",
    )
    parser.add_argument(
        "--signal-now",
        choices=["5m", "1h"],
        metavar="{5m|1h}",
        help="지정한 타임프레임의 신호를 지금 즉시 체크하고 종료",
    )
    args = parser.parse_args()

    _check_env()

    # ── 단발성 명령 처리 ──────────────────────────────

    if args.dry_run:
        from monitor.telegram_bot import send
        print("[DRY-RUN] 텔레그램 연결 테스트 중...")
        send(
            "✅ 모니터링 봇 연결 테스트 성공!\n"
            "가격 알림 / 전략 신호 / 일일 브리핑이 정상 설정되었습니다."
        )
        print("완료! 텔레그램을 확인하세요.")
        return

    if args.briefing_now:
        from monitor.telegram_bot import send
        from monitor.price_monitor import get_current_prices
        from monitor.news_monitor import build_daily_briefing
        print("[브리핑] 현재가 조회 중...")
        prices = get_current_prices()
        msg = build_daily_briefing(prices)
        print(msg)
        send(msg)
        print("완료!")
        return

    if args.signal_now:
        from monitor.telegram_bot import send
        from monitor.signal_monitor import check_signals
        print(f"[신호 체크] {args.signal_now} 신호 분석 중...")
        fired = check_signals(send, interval=args.signal_now)
        if not fired:
            msg = f"현재 {args.signal_now} 타임프레임에서 발생한 신호가 없습니다."
            print(msg)
            send(f"📭 신호 없음 ({args.signal_now})")
        else:
            print(f"발생한 신호: {len(fired)}개")
        return

    # ── 정상 실행: 스케줄러 시작 ─────────────────────

    from monitor.telegram_bot import send
    from monitor.scheduler import create_scheduler

    trade_mode = os.getenv("TRADE_MODE", "paper").upper()

    print("=" * 50)
    print("  XRP 실시간 모니터링 봇 시작")
    print("=" * 50)
    print(f"  매매 모드   : {trade_mode}")
    print(f"  가격 알림   : 매 1분 (임계값 {float(os.getenv('ALERT_THRESHOLD', '0.03'))*100:.0f}%)")
    print(f"  5분봉 신호  : 매 5분")
    print(f"  1시간봉 신호 : 매 1시간")
    print(f"  일일 브리핑 : 매일 09:00 KST")
    print("=" * 50)
    print("  종료: Ctrl+C")
    print()

    send(
        f"🚀 모니터링 봇 시작됨\n"
        f"매매 모드: {trade_mode}\n"
        f"감시 코인: XRP / BTC / ETH\n"
        f"전략: S1~S6 전체 (5m + 1h)"
    )

    scheduler = create_scheduler()
    scheduler.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n봇 종료 중...")
        scheduler.shutdown(wait=False)
        send("🛑 모니터링 봇 종료됨")
        print("완료.")


if __name__ == "__main__":
    main()
