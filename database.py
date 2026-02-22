"""
Database layer: SQLite with aiosqlite for user tracking and logs.
"""

import aiosqlite
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = "bot_database.db"

async def init_db():
    """Initialize database schema."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Users table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                daily_limit INTEGER DEFAULT 7,
                is_blocked INTEGER DEFAULT 0,
                language TEXT DEFAULT 'ru',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_active TEXT
            )
        ''')
        
        # Generations table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                mode TEXT NOT NULL,           -- txt2img / img2img / multi
                quality TEXT NOT NULL,        -- 1K / 2K / 4K
                aspect_ratio TEXT,
                prompt TEXT,
                api_cost REAL DEFAULT 0.0,
                success INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (telegram_id) REFERENCES users(telegram_id)
            )
        ''')
        
        # Pricing table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS pricing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL,
                quality TEXT NOT NULL,
                api_cost REAL DEFAULT 0.0,
                sale_price REAL DEFAULT 0.0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(mode, quality)
            )
        ''')
        
        # Insert default pricing if not exists
        default_prices = [
            ('txt2img', '1K', 0.013, 0.0),
            ('txt2img', '2K', 0.013, 0.0),
            ('txt2img', '4K', 0.024, 0.0),
            ('img2img', '1K', 0.013, 0.0),
            ('img2img', '2K', 0.013, 0.0),
            ('img2img', '4K', 0.024, 0.0),
            ('multi', '1K', 0.013, 0.0),
            ('multi', '2K', 0.013, 0.0),
            ('multi', '4K', 0.024, 0.0),
        ]
        for p in default_prices:
            await db.execute('''
                INSERT OR IGNORE INTO pricing (mode, quality, api_cost, sale_price)
                VALUES (?, ?, ?, ?)
            ''', p)
            
        await db.commit()
    logger.info("Database initialized at %s", DB_PATH)

async def upsert_user(telegram_id, username, full_name):
    """Register or update user info."""
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO users (telegram_id, username, full_name, last_active)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                last_active = excluded.last_active
        ''', (telegram_id, username, full_name, now))
        await db.commit()

async def get_user(telegram_id):
    """Get user record."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)) as cursor:
            return await cursor.fetchone()

async def set_user_language(telegram_id, language):
    """Update user language."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            UPDATE users SET language = ?
            WHERE telegram_id = ?
        ''', (language, telegram_id))
        await db.commit()

async def is_user_blocked(telegram_id):
    """Check if user is blocked."""
    user = await get_user(telegram_id)
    return user['is_blocked'] == 1 if user else False

async def log_generation(telegram_id, mode, quality, aspect_ratio, prompt, success=1):
    """Log a generation request and return its cost."""
    # Get cost from pricing table
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT api_cost FROM pricing WHERE mode = ? AND quality = ?', 
            (mode, quality)
        ) as cursor:
            row = await cursor.fetchone()
            cost = row['api_cost'] if row else 0.0
            
        await db.execute('''
            INSERT INTO generations (telegram_id, mode, quality, aspect_ratio, prompt, api_cost, success)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (telegram_id, mode, quality, aspect_ratio, prompt, cost, success))
        
        await db.commit()
        return cost

async def get_user_total_count(telegram_id):
    """Get total number of successful generations for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT COUNT(*) FROM generations 
            WHERE telegram_id = ? AND success = 1
        ''', (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_user_today_count(telegram_id):
    """Get number of successful generations today for a user."""
    today = datetime.now().strftime('%Y-%m-%d')
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT COUNT(*) FROM generations 
            WHERE telegram_id = ? AND success = 1 AND created_at LIKE ?
        ''', (telegram_id, today + '%')) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

# --- Admin Panel Helpers ---

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users ORDER BY last_active DESC') as cursor:
            return await cursor.fetchall()

async def get_user_generations(telegram_id, limit=50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT id, mode, quality, aspect_ratio, prompt, api_cost, success, created_at 
            FROM generations 
            WHERE telegram_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (telegram_id, limit)) as cursor:
            return await cursor.fetchall()

async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        stats = {}
        async with db.execute('SELECT COUNT(*) as count FROM users') as c:
            row = await c.fetchone()
            stats['total_users'] = row['count']
        async with db.execute('SELECT COUNT(*) as count FROM generations WHERE success=1') as c:
            row = await c.fetchone()
            stats['total_generations'] = row['count']
        async with db.execute('SELECT SUM(api_cost) as cost FROM generations') as c:
            row = await c.fetchone()
            stats['total_cost'] = row['cost'] or 0.0
        return stats

async def get_pricing():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM pricing') as cursor:
            return await cursor.fetchall()

async def update_pricing(pricing_id, api_cost, sale_price):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            UPDATE pricing SET api_cost = ?, sale_price = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (api_cost, sale_price, pricing_id))
        await db.commit()

async def set_user_limit(telegram_id, limit):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET daily_limit = ? WHERE telegram_id = ?', (limit, telegram_id))
        await db.commit()

async def set_user_block(telegram_id, is_blocked):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET is_blocked = ? WHERE telegram_id = ?', (1 if is_blocked else 0, telegram_id))
        await db.commit()
