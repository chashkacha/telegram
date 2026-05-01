"""
Bu faylni LOCAL kompyuteringizda bir MARTA ishlatib SESSION_STRING oling.
Keyin uni Railway'da environment variable sifatida saqlang.

    pip install pyrogram tgcrypto
    python get_session.py
"""

import asyncio
from pyrogram import Client

API_ID   = input("API_ID: ").strip()
API_HASH = input("API_HASH: ").strip()


async def main():
    async with Client(
        name="session_gen",
        api_id=int(API_ID),
        api_hash=API_HASH,
        in_memory=True,
    ) as app:
        session = await app.export_session_string()

    print("\n" + "=" * 70)
    print("✅  SESSION_STRING (buni Railway → Variables ga qo'shing):")
    print("=" * 70)
    print(session)
    print("=" * 70)
    print("\n⚠️  Bu stringni hech kimga bermang — bu sizning Telegram hisobingiz!")


asyncio.run(main())
