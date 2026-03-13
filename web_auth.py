"""
web_auth.py — Handles web authentication flow from Telegram.
"""

import logging
import secrets
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import database
from config import ADMIN_ID, ADMIN_URL

logger = logging.getLogger(__name__)

async def web_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin approves web access."""
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Нет прав.", show_alert=True)
        return

    user_id = int(query.data.replace("web_approve_", ""))
    token = secrets.token_urlsafe(16)
    
    # Save to DB
    await database.create_web_session(token, user_id, balance=3)
    
    # Notify User
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Войти в Web-интерфейс", url=f"{ADMIN_URL}/auth?token={token}")]
    ])
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="✅ <b>Ваш доступ одобрен!</b>\nИспользуйте кнопку ниже для входа. Ссылка одноразовая.",
            reply_markup=kb,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")

    await query.answer("Доступ одобрен")
    await query.edit_message_text(
        query.message.text_html + "\n\n✅ <b>Одобрено.</b>",
        parse_mode=ParseMode.HTML
    )

async def web_deny_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin denies web access."""
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Нет прав.", show_alert=True)
        return

    user_id = int(query.data.replace("web_deny_", ""))
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ <b>В доступе к Web-интерфейсу отказано.</b>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")

    await query.answer("Отказано")
    await query.edit_message_text(
        query.message.text_html + "\n\n❌ <b>Отклонено.</b>",
        parse_mode=ParseMode.HTML
    )
