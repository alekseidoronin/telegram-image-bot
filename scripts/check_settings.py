import asyncio
import database

async def check():
    await database.init_db()
    settings = ["YOOMONEY_WALLET", "YOOMONEY_SECRET", "NOWPAYMENTS_API_KEY", "NOWPAYMENTS_IPN_SECRET"]
    for s in settings:
        val = await database.get_setting(s)
        print(f"{s}: {'SET' if val else 'NOT SET'}")

asyncio.run(check())
