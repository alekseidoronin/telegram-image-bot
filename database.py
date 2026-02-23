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
                is_admin INTEGER DEFAULT 0,
                language TEXT DEFAULT 'ru',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_active TEXT
            )
        ''')
        
        # Migration: add is_admin column if it doesn't exist
        try:
            await db.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0')
            await db.commit()
        except:
            pass # Already exists
        
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
            
        # Settings table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
            
        await db.commit()
    logger.info("Database initialized at %s", DB_PATH)

async def get_setting(key, default=None):
    """Retrieve a setting from the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
            row = await cursor.fetchone()
            return row['value'] if row else default

async def set_setting(key, value):
    """Save or update a setting in the database."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        ''', (key, str(value)))
        await db.commit()

async def get_all_settings():
    """Get all settings as a dictionary."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM settings') as cursor:
            rows = await cursor.fetchall()
            return {row['key']: row['value'] for row in rows}

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

async def is_user_admin(telegram_id):
    """Check if user is admin."""
    # Hardcoded superadmin
    if telegram_id == 632600126:
        return True
    user = await get_user(telegram_id)
    return user['is_admin'] == 1 if user else False

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

async def decrease_user_balance(telegram_id):
    """Decrease user balance by 1."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET daily_limit = daily_limit - 1 WHERE telegram_id = ? AND daily_limit > 0', (telegram_id,))
        await db.commit()

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
    """Update user balance directly."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET daily_limit = ? WHERE telegram_id = ?', (limit, telegram_id))
        await db.commit()

async def set_user_block(telegram_id, is_blocked):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET is_blocked = ? WHERE telegram_id = ?', (1 if is_blocked else 0, telegram_id))
        await db.commit()

async def set_user_admin_status(telegram_id, is_admin):
    """Update admin status for a user."""
    # Prevent removing superadmin status
    if telegram_id == 632600126 and not is_admin:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET is_admin = ? WHERE telegram_id = ?', (1 if is_admin else 0, telegram_id))
        await db.commit()

async def delete_user(telegram_id):
    """Delete a user and all their generations."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM generations WHERE telegram_id = ?', (telegram_id,))
        await db.execute('DELETE FROM users WHERE telegram_id = ?', (telegram_id,))
        await db.commit()


async def get_stats_for_period(date_from=None, date_to=None):
    """Get generation stats for a specific period."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        stats = {}
        where = "WHERE 1=1"
        params = []
        if date_from:
            where += " AND created_at >= ?"
            params.append(date_from)
        if date_to:
            where += " AND created_at <= ?"
            params.append(date_to + " 23:59:59")

        async with db.execute(
            f'SELECT COUNT(*) as count FROM generations {where} AND success=1', params
        ) as c:
            row = await c.fetchone()
            stats['generations'] = row['count']
        async with db.execute(
            f'SELECT COALESCE(SUM(api_cost), 0) as cost FROM generations {where}', params
        ) as c:
            row = await c.fetchone()
            stats['api_cost'] = row['cost']

        # Calculate sale revenue
        async with db.execute('''
            SELECT COALESCE(SUM(p.sale_price), 0) as revenue
            FROM generations g
            JOIN pricing p ON g.mode = p.mode AND g.quality = p.quality
        ''' + where.replace('created_at', 'g.created_at') + ' AND g.success=1', params
        ) as c:
            row = await c.fetchone()
            stats['revenue'] = row['revenue']

        return stats


async def get_today_stats():
    """Get today's generation stats."""
    today = datetime.now().strftime('%Y-%m-%d')
    return await get_stats_for_period(today, today)


async def get_month_stats():
    """Get this month's generation stats."""
    month_start = datetime.now().strftime('%Y-%m-01')
    return await get_stats_for_period(month_start)
