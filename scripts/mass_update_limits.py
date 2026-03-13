import asyncio
import aiosqlite
import os

DB_PATH = '/home/debian/Telegram-image-bot/bot_database.db'

async def main():
    if not os.path.exists(DB_PATH):
        print(f'Error: {DB_PATH} not found')
        return

    async with aiosqlite.connect(DB_PATH) as db:
        # Check current status
        async with db.execute('SELECT COUNT(*) FROM users WHERE is_admin = 0 AND daily_limit > 5') as cursor:
            count = (await cursor.fetchone())[0]
            print(f'Found {count} non-admin users with limit > 5')

        if count > 0:
            await db.execute('UPDATE users SET daily_limit = 5 WHERE is_admin = 0 AND daily_limit > 5')
            await db.commit()
            print('Updated user limits successfully.')
        else:
            print('No users needed updating.')

if __name__ == '__main__':
    asyncio.run(main())
