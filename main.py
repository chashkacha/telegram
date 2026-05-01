import asyncio
import logging
import os
import sys

from pyrogram import Client
from pyrogram.errors import FloodWait

from config import API_ID, API_HASH, BOT_TOKEN, SESSION_STRING, DOWNLOAD_DIR
from handlers.handlers import register_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def main():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    user = Client(
        "user_session",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION_STRING,
        no_updates=True,
    )

    bot = Client(
        "bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
    )

    register_all(bot, user)
    logger.info("🚀 Bot ishga tushmoqda...")

    while True:
        try:
            async with user, bot:
                logger.info("✅ User client ulandi")
                logger.info("✅ Bot client ulandi")
                logger.info("🤖 Bot ishlayapti. To'xtatish uchun Ctrl+C")
                await asyncio.Event().wait()
        except FloodWait as e:
            wait = e.value
            logger.warning(f"⏳ FloodWait: {wait}s kutilmoqda...")
            await asyncio.sleep(wait + 5)
            logger.info("🔄 Qayta ulanish...")
        except (KeyboardInterrupt, SystemExit):
            logger.info("🛑 Bot to'xtatildi.")
            break


if __name__ == "__main__":
    asyncio.run(main())
