import aiosqlite
import bcrypt
import asyncio
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

DB_PATH = 'bot_database.db'
logger = logging.getLogger(__name__)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                daily_limit INTEGER DEFAULT 3,
                is_blocked INTEGER DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                language TEXT DEFAULT 'ru',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_active TEXT
            )
        ''')
        # Migration: add web_account_id link to WebAccounts, if ещё нет
        try:
            await db.execute('ALTER TABLE users ADD COLUMN web_account_id INTEGER')
        except Exception:
            pass
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                mode TEXT,
                quality TEXT,
                aspect_ratio TEXT,
                prompt TEXT,
                prompt_embedding BLOB,
                api_cost REAL DEFAULT 0.0,
                success INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS pricing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT,
                quality TEXT,
                api_cost REAL,
                sale_price REAL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT,
                action TEXT,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS EmailAccessLog (
                email TEXT PRIMARY KEY,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                order_id TEXT PRIMARY KEY,
                user_id INTEGER,
                amount REAL,
                generations INTEGER,
                gateway TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS invite_tokens (
                token TEXT PRIMARY KEY,
                is_used INTEGER DEFAULT 0,
                expires_at TEXT NOT NULL,
                fingerprint TEXT,
                ip_address TEXT,
                user_agent TEXT,
                generations_left INTEGER DEFAULT 3,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                email TEXT,
                account_id INTEGER
            )
        ''')
        # Migration: add email and account_id if table already existed
        try:
            await db.execute('ALTER TABLE invite_tokens ADD COLUMN email TEXT')
        except Exception:
            pass
        try:
            await db.execute('ALTER TABLE invite_tokens ADD COLUMN account_id INTEGER')
        except Exception:
            pass

        await db.execute('''
            CREATE TABLE IF NOT EXISTS WebSessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER,
                balance INTEGER DEFAULT 3,
                is_used INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS WebAccounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                password_hash BLOB,
                display_name TEXT,
                is_admin INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_login TEXT
            )
        ''')

        # One-time migration from legacy WebUsers to WebAccounts (email only)
        try:
            await _migrate_webusers_to_webaccounts(db)
        except Exception as e:
            logger.exception("WebUsers → WebAccounts migration failed: %s", e)

        # Ensure there is at least one web admin account
        try:
            await _ensure_web_admin_account(db)
        except Exception as e:
            logger.exception("Failed to ensure web admin account: %s", e)

        await db.execute('''
            CREATE TABLE IF NOT EXISTS WebUsers (
                token TEXT PRIMARY KEY,
                email TEXT,
                display_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await init_pricing(db)

        # Migration: Add prompt_embedding if missing
        try:
            await db.execute('ALTER TABLE generations ADD COLUMN prompt_embedding BLOB')
        except:
            pass

        await db.commit()

    logger.info(f"Database initialized at {DB_PATH}")



async def init_pricing(db):
    # Check if pricing table needs simplification (user wants only 3 prices for 1K, 2K, 4K)
    async with db.execute('SELECT COUNT(*) FROM pricing') as cursor:
        count = (await cursor.fetchone())[0]
        if count != 3:
            await db.execute('DELETE FROM pricing')
            # Base Gemini Flash 3.1 pricing (approx):
            # 1K  ≈ $0.045, 2K ≈ $0.09, 4K ≈ $0.18
            default_pricing = [
                ('-', '1K', 0.045, 0.19),
                ('-', '2K', 0.090, 0.29),
                ('-', '4K', 0.180, 0.49),
            ]
            await db.executemany(
                '''
                INSERT INTO pricing (mode, quality, api_cost, sale_price)
                VALUES (?, ?, ?, ?)
                ''',
                default_pricing,
            )

async def get_setting(key):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR REPLACE INTO settings (key, value)
            VALUES (?, ?)
        ''', (key, value))
        await db.commit()

async def get_all_settings():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM settings') as cursor:
            rows = await cursor.fetchall()
            return {row['key']: row['value'] for row in rows}

async def upsert_user(telegram_id, username, full_name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO users (telegram_id, username, full_name, daily_limit, last_active)
            VALUES (?, ?, ?, 3, CURRENT_TIMESTAMP)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                last_active = CURRENT_TIMESTAMP
        ''', (telegram_id, username, full_name))
        await db.commit()

async def get_user(telegram_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,)) as cursor:
            return await cursor.fetchone()

async def set_user_language(telegram_id, language):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            UPDATE users SET language = ?
            WHERE telegram_id = ?
        ''', (language, telegram_id))
        await db.commit()

async def is_user_blocked(telegram_id):
    user = await get_user(telegram_id)
    return user['is_blocked'] == 1 if user else False

async def is_user_admin(telegram_id):
    from config import ADMIN_ID
    if telegram_id == ADMIN_ID:
        return True
    user = await get_user(telegram_id)
    return user['is_admin'] == 1 if user else False

async def log_generation(telegram_id, mode, quality, aspect_ratio, prompt, success=1, embedding=None, api_cost: float | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # If api_cost is not provided explicitly, fall back to pricing table
        cost = api_cost
        if cost is None:
            async with db.execute(
                'SELECT api_cost FROM pricing WHERE quality = ?', 
                (quality,)
            ) as cursor:
                row = await cursor.fetchone()
                cost = row['api_cost'] if row else 0.0
        
        await db.execute('''
            INSERT INTO generations (telegram_id, mode, quality, aspect_ratio, prompt, prompt_embedding, api_cost, success)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (telegram_id, mode, quality, aspect_ratio, prompt, embedding, cost, success))
        
        await db.commit()
        return cost

async def search_similar_generations(telegram_id, query_embedding, limit=5):
    """
    Search for semantically similar generations using cosine similarity.
    Note: In SQLite, we'll fetch results and compute similarity in Python for simplicity.
    """
    import numpy as np
    from numpy.linalg import norm

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Fetch generations only for this user that have embeddings
        async with db.execute(
            'SELECT id, prompt, prompt_embedding FROM generations WHERE telegram_id = ? AND prompt_embedding IS NOT NULL AND success = 1',
            (telegram_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            
        if not rows:
            return []

        results = []
        q_vec = np.frombuffer(query_embedding, dtype=np.float32)

        for row in rows:
            db_vec = np.frombuffer(row['prompt_embedding'], dtype=np.float32)
            # Cosine similarity: (A . B) / (||A|| * ||B||)
            # If vectors are normalized, it's just A . B
            similarity = np.dot(q_vec, db_vec) / (norm(q_vec) * norm(db_vec))
            results.append({
                'id': row['id'],
                'prompt': row['prompt'],
                'similarity': float(similarity)
            })

        # Sort by similarity descending
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:limit]

async def decrease_user_balance(telegram_id, amount=1):
    async with aiosqlite.connect(DB_PATH) as db:
        # -1 означает безлимит — не уменьшаем баланс
        await db.execute(
            '''
            UPDATE users
            SET daily_limit = CASE
                WHEN daily_limit = -1 THEN -1
                ELSE daily_limit - ?
            END
            WHERE telegram_id = ? AND (daily_limit >= ? OR daily_limit = -1)
            ''',
            (amount, telegram_id, amount),
        )
        await db.commit()

async def add_user_balance(telegram_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            UPDATE users
            SET daily_limit = CASE
                WHEN daily_limit = -1 THEN -1
                ELSE daily_limit + ?
            END
            WHERE telegram_id = ?
            ''',
            (amount, telegram_id),
        )
        await db.commit()

async def log_payment(telegram_id, stars_amount, generations_added, payment_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO payments (telegram_id, stars_amount, generations_added, payment_id)
            VALUES (?, ?, ?, ?)
        ''', (telegram_id, stars_amount, generations_added, payment_id))
        await db.commit()

async def get_user_total_count(telegram_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT COUNT(*) FROM generations 
            WHERE telegram_id = ? AND success = 1
        ''', (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT telegram_id, username, full_name, daily_limit, is_blocked, is_admin, language, web_account_id, datetime(created_at, '+3 hours') as created_at, datetime(last_active, '+3 hours') as last_active FROM users ORDER BY last_active DESC") as cursor:
            return await cursor.fetchall()

async def get_user_generations(telegram_id, limit=50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT id, telegram_id, mode, quality, aspect_ratio, prompt, api_cost, success, 
            datetime(created_at, '+3 hours') as created_at 
            FROM generations WHERE telegram_id = ? ORDER BY created_at DESC LIMIT ?
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

async def get_admin_stats():
    return await get_stats()

async def get_pricing():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, mode, quality, api_cost, sale_price, datetime(updated_at, '+3 hours') as updated_at FROM pricing") as cursor:
            return await cursor.fetchall()

async def update_pricing(pricing_id, api_cost, sale_price):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            UPDATE pricing SET api_cost = ?, sale_price = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (api_cost, sale_price, pricing_id))
        await db.commit()


async def get_user_by_web_account(web_account_id: int):
    """Return user row linked to given WebAccount id, if any."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE web_account_id = ? LIMIT 1",
            (web_account_id,),
        ) as cursor:
            return await cursor.fetchone()

async def set_user_limit(telegram_id, limit):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET daily_limit = ? WHERE telegram_id = ?', (limit, telegram_id))
        await db.commit()

async def add_user_limit(telegram_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            UPDATE users
            SET daily_limit = CASE
                WHEN daily_limit = -1 THEN -1
                ELSE daily_limit + ?
            END
            WHERE telegram_id = ? AND daily_limit >= 0
            ''',
            (amount, telegram_id),
        )
        await db.commit()

async def set_user_block(telegram_id, is_blocked):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET is_blocked = ? WHERE telegram_id = ?', (1 if is_blocked else 0, telegram_id))
        await db.commit()

async def set_user_admin_status(telegram_id, is_admin):
    if telegram_id == 632600126 and not is_admin:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET is_admin = ? WHERE telegram_id = ?', (1 if is_admin else 0, telegram_id))
        await db.commit()

async def delete_user(telegram_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM generations WHERE telegram_id = ?', (telegram_id,))
        await db.execute('DELETE FROM users WHERE telegram_id = ?', (telegram_id,))
        await db.commit()

async def log_audit(user, action, details):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO audit_logs (user, action, details)
            VALUES (?, ?, ?)
        ''', (user, action, details))
        await db.commit()

async def get_audit_logs(limit=100):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, user, action, details, datetime(created_at, '+3 hours') as created_at FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,)) as cursor:
            return await cursor.fetchall()

async def get_stats_for_period(date_from=None, date_to=None):
    """Get generation stats for a specific period."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        stats = {}
        # We store timestamps in UTC, but for reporting we want Moscow time (UTC+3).
        # Convert created_at to Moscow time inside SQLite and compare against local (MSK) dates.
        created_msk = "datetime(created_at, '+3 hours')"
        where = "WHERE 1=1"
        params = []
        if date_from:
            where += f" AND {created_msk} >= ?"
            params.append(f"{date_from} 00:00:00")
        if date_to:
            where += f" AND {created_msk} <= ?"
            params.append(f"{date_to} 23:59:59")

        async with db.execute(
            f"SELECT COUNT(*) as count FROM generations {where} AND success=1", params
        ) as c:
            row = await c.fetchone()
            stats["generations"] = row["count"]
        async with db.execute(
            f"SELECT COALESCE(SUM(api_cost), 0) as cost FROM generations {where}", params
        ) as c:
            row = await c.fetchone()
            stats["api_cost"] = row["cost"]

        # Calculate sale revenue
        created_msk_g = "datetime(g.created_at, '+3 hours')"
        where_g = "WHERE 1=1"
        params_g = []
        if date_from:
            where_g += f" AND {created_msk_g} >= ?"
            params_g.append(f"{date_from} 00:00:00")
        if date_to:
            where_g += f" AND {created_msk_g} <= ?"
            params_g.append(f"{date_to} 23:59:59")

        async with db.execute(
            f"""SELECT COALESCE(SUM(p.sale_price), 0) as revenue
            FROM generations g
            JOIN pricing p ON g.quality = p.quality
            {where_g} AND g.success=1""",
            params_g,
        ) as c:
            row = await c.fetchone()
            stats["revenue"] = row["revenue"]

        return stats


async def get_today_stats():
    """Get today's generation stats."""
    # Use Moscow time for "today" in dashboard
    today = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d")
    return await get_stats_for_period(today, today)


async def get_month_stats():
    """Get this month's generation stats."""
    # Use Moscow time for "this month" in dashboard
    month_start = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-01")
    return await get_stats_for_period(month_start)

# ── Transaction Management ───────────────────────────────────────────────────

async def create_transaction(order_id, user_id, amount, generations, gateway):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO transactions (order_id, user_id, amount, generations, gateway)
            VALUES (?, ?, ?, ?, ?)
        ''', (order_id, user_id, amount, generations, gateway))
        await db.commit()

async def get_transaction(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM transactions WHERE order_id = ?', (order_id,)) as cursor:
            return await cursor.fetchone()

async def complete_transaction(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM transactions WHERE order_id = ?', (order_id,)) as cursor:
            tx = await cursor.fetchone()
            
        if not tx or tx['status'] == 'paid':
            return False
            
        # 1. Update status
        await db.execute('UPDATE transactions SET status = "paid" WHERE order_id = ?', (order_id,))
        
        # 2. Add balance to user
        await db.execute('UPDATE users SET daily_limit = daily_limit + ? WHERE telegram_id = ?', (tx['generations'], tx['user_id']))
        
        await db.commit()
        return True

async def get_all_transactions(limit=100):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT t.order_id, t.user_id, t.amount, t.generations, t.gateway, t.status, 
            datetime(t.created_at, '+3 hours') as created_at, u.full_name, u.username 
            FROM transactions t
            LEFT JOIN users u ON t.user_id = u.telegram_id
            ORDER BY t.created_at DESC 
            LIMIT ?
        ''', (limit,)) as cursor:
            return await cursor.fetchall()


async def reject_transaction(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM transactions WHERE order_id = ?", (order_id,)) as cursor:
            tx = await cursor.fetchone()
        if not tx or tx["status"] != "pending":
            return False
        await db.execute("UPDATE transactions SET status = 'rejected' WHERE order_id = ?", (order_id,))
        await db.commit()
        return True

async def restore_transaction(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM transactions WHERE order_id = ?", (order_id,)) as cursor:
            tx = await cursor.fetchone()
        if not tx or tx["status"] != "rejected":
            return False
        await db.execute("UPDATE transactions SET status = 'pending' WHERE order_id = ?", (order_id,))
        await db.commit()
        return True


# ── Invite Token Management ──────────────────────────────────────────────────

async def create_invite_token(token: str, expires_at: str, email: str | None = None, account_id: int | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO invite_tokens (token, is_used, expires_at, generations_left, email, account_id)
            VALUES (?, 0, ?, 3, ?, ?)
        ''', (token, expires_at, (email or "").lower().strip() or None, account_id))
        await db.commit()


async def get_invite_token_by_email(email: str):
    """Return first (unused preferred) invite token for this email."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM invite_tokens WHERE LOWER(TRIM(email)) = ? ORDER BY is_used ASC, created_at DESC LIMIT 1",
            (email.lower().strip(),),
        ) as c:
            return await c.fetchone()


async def set_invite_account_id(token: str, account_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE invite_tokens SET account_id = ? WHERE token = ?", (account_id, token))
        await db.commit()


async def get_invite_token(token: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM invite_tokens WHERE token = ?', (token,)) as cursor:
            return await cursor.fetchone()

async def delete_invite_token(token: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM invite_tokens WHERE token = ?', (token,))
        await db.commit()

async def activate_invite_token(token: str, fingerprint: str, ip_address: str, user_agent: str):
    """Mark token as used and record fingerprint/IP on first visit."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            UPDATE invite_tokens
            SET is_used = 1, fingerprint = ?, ip_address = ?, user_agent = ?
            WHERE token = ? AND is_used = 0
        ''', (fingerprint, ip_address, user_agent, token))
        await db.commit()

async def claim_invite_generation(token: str, amount: int = 1) -> bool:
    """Decrement generations_left by `amount`. Returns True if successful."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT generations_left FROM invite_tokens WHERE token = ?', (token,)
        ) as cursor:
            row = await cursor.fetchone()
        if not row or row['generations_left'] < amount:
            return False
        await db.execute(
            'UPDATE invite_tokens SET generations_left = generations_left - ? WHERE token = ?',
            (amount, token)
        )
        await db.commit()
        return True

async def get_invite_generations_left(token: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT generations_left FROM invite_tokens WHERE token = ?', (token,)
        ) as cursor:
            row = await cursor.fetchone()
        return row['generations_left'] if row else 0

async def get_all_invite_tokens(limit: int = 100):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT * FROM invite_tokens ORDER BY created_at DESC LIMIT ?', (limit,)
        ) as cursor:
            return await cursor.fetchall()


# ── Email Access Log ────────────────────────────────────────────────────────────

async def is_email_used(email: str) -> bool:
    """Return True if this email has already been used to request web access."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT 1 FROM EmailAccessLog WHERE email = ? LIMIT 1', (email.lower(),)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def mark_email_used(email: str):
    """Mark email as used in EmailAccessLog (idempotent)."""
    normalized = email.lower()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT OR IGNORE INTO EmailAccessLog (email)
            VALUES (?)
            ''',
            (normalized,),
        )
        await db.commit()

# ── Web Sessions ─────────────────────────────────────────────────────────────

async def create_web_session(token: str, user_id: int = 0, balance: int = 3):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO WebSessions (token, user_id, balance)
            VALUES (?, ?, ?)
        ''', (token, user_id, balance))
        await db.commit()

async def get_web_session(token: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM WebSessions WHERE token = ? AND is_used = 0', (token,)) as cursor:
            return await cursor.fetchone()


async def get_web_session_by_account_id(account_id: int):
    """Return existing WebSession for this account (user_id = account_id), if any."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT * FROM WebSessions WHERE user_id = ? AND is_used = 0 LIMIT 1',
            (account_id,),
        ) as cursor:
            return await cursor.fetchone()


async def get_web_session_balance(token: str) -> int:
    """Return current balance (generations left) for a WebSession token."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT balance FROM WebSessions WHERE token = ?',
            (token,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def delete_web_session(token: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM invite_tokens WHERE token = ?', (token,))
        await db.execute('DELETE FROM WebSessions WHERE token = ?', (token,))
        await db.commit()

async def get_all_web_sessions(limit: int = 100):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT token, user_id, balance, is_used, datetime(created_at, '+3 hours') AS created_at "
            "FROM WebSessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            return await cursor.fetchall()


# ── Web Users (email / display name) ───────────────────────────────────────────

async def upsert_web_user(token: str, email: str):
    """Create or update a WebUser identified by invite/web token."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT INTO WebUsers (token, email)
            VALUES (?, ?)
            ON CONFLICT(token) DO UPDATE SET email = excluded.email
            ''',
            (token, email.lower()),
        )
        await db.commit()


async def get_web_user(token: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM WebUsers WHERE token = ?', (token,)) as cursor:
            return await cursor.fetchone()


async def set_web_user_display_name(token: str, name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE WebUsers SET display_name = ? WHERE token = ?',
            (name.strip(), token),
        )
        await db.commit()


# ── Web Accounts (email + password) ───────────────────────────────────────────

async def _migrate_webusers_to_webaccounts(db):
    """
    One-time migration: take distinct emails from WebUsers and create WebAccounts without passwords.
    Safe to call multiple times thanks to UNIQUE(email).
    """
    # Check if WebUsers table exists
    try:
        async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='WebUsers'") as c:
            row = await c.fetchone()
            if not row:
                return
    except Exception:
        return

    async with db.execute("SELECT DISTINCT LOWER(email) AS email FROM WebUsers WHERE email IS NOT NULL AND email <> ''") as c:
        rows = await c.fetchall()
    for r in rows:
        email = r[0]
        if not email:
            continue
        try:
            await db.execute(
                '''
                INSERT OR IGNORE INTO WebAccounts (email, is_admin)
                VALUES (?, 0)
                ''',
                (email,),
            )
        except Exception:
            # ignore per-row failures, continue
            continue


async def _ensure_web_admin_account(db):
    """
    Ensure there is at least one admin WebAccount.
    Uses a fixed email and bootstrap password for the platform owner.
    """
    admin_email = "neonixys@gmail.ru"
    password = "admin123"

    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    await db.execute(
        """
        INSERT INTO WebAccounts (email, password_hash, display_name, is_admin)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(email) DO UPDATE SET
            password_hash = excluded.password_hash,
            display_name  = excluded.display_name,
            is_admin      = 1
        """,
        (admin_email.lower(), pw_hash, "Admin"),
    )
    logger.info("Ensured WebAccount admin with email %s", admin_email)


async def get_web_account_by_email(email: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM WebAccounts WHERE email = ? LIMIT 1",
            (email.lower(),),
        ) as c:
            return await c.fetchone()


async def create_web_account(email: str, password: str, is_admin: bool = False, display_name: str = ""):
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            '''
            INSERT INTO WebAccounts (email, password_hash, display_name, is_admin)
            VALUES (?, ?, ?, ?)
            ''',
            (email.lower(), pw_hash, display_name or "", 1 if is_admin else 0),
        )
        await db.commit()


async def get_web_account_by_id(account_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM WebAccounts WHERE id = ? LIMIT 1",
            (account_id,),
        ) as c:
            return await c.fetchone()


async def link_user_to_web_account(telegram_id: int, email: str | None):
    """
    Link Telegram user to WebAccount by email.
    If email is empty, web_account_id will be cleared.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        if not email:
            await db.execute(
                "UPDATE users SET web_account_id = NULL WHERE telegram_id = ?",
                (telegram_id,),
            )
            await db.commit()
            return

        normalized = email.lower().strip()
        if "@" not in normalized:
            return

        # Find or create WebAccount for this email
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM WebAccounts WHERE email = ? LIMIT 1",
            (normalized,),
        ) as c:
            acc = await c.fetchone()

        if not acc:
            await db.execute(
                "INSERT INTO WebAccounts (email, display_name, is_admin) VALUES (?, ?, 0)",
                (normalized, normalized),
            )
            await db.commit()
            async with db.execute(
                "SELECT * FROM WebAccounts WHERE email = ? LIMIT 1",
                (normalized,),
            ) as c:
                acc = await c.fetchone()

        if not acc:
            return

        await db.execute(
            "UPDATE users SET web_account_id = ? WHERE telegram_id = ?",
            (acc["id"], telegram_id),
        )
        await db.commit()


async def get_or_create_web_account_for_invite(email: str):
    """
    Return WebAccount for this email. If none exists, create one (no password).
    Returns (row, created: bool).
    """
    email = (email or "").lower().strip()
    if not email or "@" not in email:
        return None, False
    acc = await get_web_account_by_email(email)
    if acc:
        return acc, False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO WebAccounts (email, display_name, is_admin) VALUES (?, '', 0)",
            (email,),
        )
        await db.commit()
    acc = await get_web_account_by_email(email)
    return acc, True


async def set_web_account_password(account_id: int, new_password_hash: bytes):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE WebAccounts SET password_hash = ?, last_login = CURRENT_TIMESTAMP WHERE id = ?",
            (new_password_hash, account_id),
        )
        await db.commit()


async def set_web_account_display_name(account_id: int, display_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE WebAccounts SET display_name = ? WHERE id = ?",
            (display_name.strip(), account_id),
        )
        await db.commit()
