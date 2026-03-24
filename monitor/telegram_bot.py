# =============================================================================
# monitor/telegram_bot.py — 텔레그램 메시지 발송 유틸
# =============================================================================

import os
import asyncio
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


async def _send_async(text: str) -> None:
    """텔레그램 메시지 비동기 발송 (최대 4096자 자동 분할)."""
    if not _TOKEN or not _CHAT_ID:
        print("[telegram] TOKEN 또는 CHAT_ID 미설정 — 콘솔 출력으로 대체:")
        print(text)
        return

    bot = Bot(token=_TOKEN)
    # 텔레그램 메시지 최대 4096자 제한 처리
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    async with bot:
        for chunk in chunks:
            await bot.send_message(chat_id=_CHAT_ID, text=chunk)


def send(text: str) -> None:
    """동기 인터페이스 — 스케줄러·모니터에서 호출."""
    try:
        asyncio.run(_send_async(text))
    except RuntimeError:
        # 이미 실행 중인 이벤트 루프 안에서 호출된 경우
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_send_async(text))
