"""
web_invite_handlers.py — Telegram flow for manual web access approval via email.
"""

import logging
import secrets
import re
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

import database
import mailer
from config import ADMIN_ID, ADMIN_URL, CHOOSE_MODE, AWAITING_WEB_EMAIL

logger = logging.getLogger(__name__)

# ── Callback prefixes ─────────────────────────────────────────────────────────
CB_APPROVE = "approve_web_"   # + user_id
CB_REJECT  = "decline_web_"   # + user_id
CB_EM_APP  = "em_app_"        # + b64_email
CB_EM_DEN  = "em_den_"        # + b64_email

# ── Entry Point ───────────────────────────────────────────────────────────────

async def webaccess_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User sends /webaccess or clicks button.
    Starts email collection flow.
    """
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    logger.info(f"webaccess_command: user {user.id}")

    # Check existing request
    req = await database.get_web_request(user.id)
    
    if req:
        if req['status'] == 'pending':
            text = "⏳ <b>Ваша заявка на рассмотрении.</b>\nМы сообщим вам, как только администратор одобрит доступ."
            await _reply(update, text)
            return ConversationHandler.END
        elif req['status'] == 'approved':
            text = f"✅ <b>Доступ уже предоставлен!</b>\nПроверьте вашу почту или используйте ссылку: {ADMIN_URL}/try?token={req['token']}"
            await _reply(update, text)
            return ConversationHandler.END

    # If no request or declined, ask for email
    text = (
        "🌐 <b>Запрос доступа к Web-платформе</b>\n\n"
        "Для получения персональной ссылки, пожалуйста, <b>введите ваш Email</b>.\n"
        "На него придет подтверждение после одобрения администратором."
    )
    await _reply(update, text)
    return AWAITING_WEB_EMAIL

async def handle_web_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Process email input from user.
    """
    user = update.effective_user
    email = update.message.text.strip() if update.message else ""

    # Simple email validation
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await update.message.reply_text("❌ <b>Некорректный Email.</b> Пожалуйста, попробуйте еще раз или нажмите /cancel.")
        return AWAITING_WEB_EMAIL

    # Save request
    username = f"@{user.username}" if user.username else str(user.id)
    await database.create_web_request(user.id, username, email=email)

    await update.message.reply_text(
        "✅ <b>Email принят!</b>\nЗаявка отправлена администратору. Ожидайте уведомления здесь и на почте.",
        parse_mode=ParseMode.HTML
    )

    # Notify Admin
    card = (
        "👤 <b>Новый запрос Web-доступа!</b>\n"
        f"Пользователь: {username}\n"
        f"Email: <code>{email}</code>\n"
        f"ID: <code>{user.id}</code>\n\n"
        "Предоставить доступ?"
    )
    approve_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"{CB_APPROVE}{user.id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"{CB_REJECT}{user.id}"),
        ]
    ])

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=card,
            parse_mode=ParseMode.HTML,
            reply_markup=approve_kb
        )
    except Exception as e:
        logger.error(f"handle_web_email: failed to notify admin: {e}")

    return CHOOSE_MODE # Back to main menu

# ── Admin callbacks ───────────────────────────────────────────────────────────

async def webinv_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin approves. Generates token, updates DB, sends email."""
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Нет прав.", show_alert=True)
        return

    user_id = int(query.data[len(CB_APPROVE):])
    req = await database.get_web_request(user_id)
    
    if not req:
        await query.answer("Заявка не найдена.")
        return

    email = req.get('email')

    # Check if invite token already exists for this email
    existing_invite = await database.get_invite_token_by_email(email)
    if existing_invite:
        if existing_invite['is_used'] == 0:
            token = existing_invite['token']
        else:
            await database.delete_invite_token(existing_invite['token'])
            token = secrets.token_urlsafe(16)
            expires_at = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
            await database.create_invite_token(token, expires_at, email=email)
    else:
        token = secrets.token_urlsafe(16)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
        await database.create_invite_token(token, expires_at, email=email)
    
    # Update state
    await database.update_web_request(user_id, 'approved', token)
    
    # Send Email
    link = f"{ADMIN_URL}/try?token={token}"
    mail_sent = mailer.send_access_link(email, link)

    # Notify User in TG
    try:
        tg_msg = "✅ <b>Доступ одобрен!</b>\n"
        if mail_sent:
            tg_msg += f"Мы отправили вашу персональную ссылку на почту <b>{email}</b>."
        else:
            tg_msg += f"Ваша ссылка для входа: {link}"
        
        await context.bot.send_message(chat_id=user_id, text=tg_msg, parse_mode=ParseMode.HTML)
    except:
        pass

    await query.answer("Одобрено" + (" (Email отправлен)" if mail_sent else ""))
    await query.edit_message_text(
        query.message.text_html + f"\n\n✅ <b>Одобрено.</b> { 'Email отправлен' if mail_sent else 'Ошибка почты' }",
        parse_mode=ParseMode.HTML
    )

async def webinv_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin rejects."""
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Нет прав.", show_alert=True)
        return

    user_id = int(query.data[len(CB_REJECT):])
    await database.update_web_request(user_id, 'declined')

    try:
        await context.bot.send_message(chat_id=user_id, text="❌ <b>В доступе к Web-интерфейсу отказано.</b>", parse_mode=ParseMode.HTML)
    except:
        pass

    await query.answer("Отклонено")
    await query.edit_message_text(
        query.message.text_html + "\n\n❌ <b>Отклонено.</b>",
        parse_mode=ParseMode.HTML
    )

async def email_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin approves email request from landing."""
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Нет прав.", show_alert=True)
        return

    import base64
    b64_part = query.data[len(CB_EM_APP):]
    # Add padding if needed
    missing_padding = len(b64_part) % 4
    if missing_padding:
        b64_part += '=' * (4 - missing_padding)
    
    try:
        email = base64.urlsafe_b64decode(b64_part).decode()
    except Exception as e:
        await query.answer(f"Ошибка декодирования: {e}")
        return

    # Check if session already exists for this email
    existing_session = await database.get_web_session_by_email(email)
    
    if existing_session:
        # If it exists and NOT used, we can just resend the same link
        if existing_session['is_used'] == 0:
            token = existing_session['token']
        else:
            # If it was used, maybe they need a new one? 
            # Or we just update the existing record. 
            # Based on user request "Only one record", let's replace the old one.
            await database.delete_web_session(existing_session['token'])
            token = secrets.token_urlsafe(24)
            await database.create_web_session(token, user_id=0, balance=3, email=email)
    else:
        token = secrets.token_urlsafe(24)
        await database.create_web_session(token, user_id=0, balance=3, email=email)

    # link = "https://neuronanobanana.duckdns.org/auth?token={token}"
    link = f"{ADMIN_URL}/auth?token={token}"
    
    # Send mail
    success = mailer.send_access_link(email, link)

    await query.answer("✅ Одобрено! Письмо отправлено." if success else "⚠️ Одобрено, но ошибка почты.")
    await query.edit_message_text(
        query.message.text_html + f"\n\n✅ <b>Одобрено для {email}.</b>" + (" (Письмо ушло)" if success else " (Ошибка SMTP)"),
        parse_mode=ParseMode.HTML
    )

async def email_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin rejects email request."""
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ Нет прав.", show_alert=True)
        return

    await query.answer("Отклонено.")
    await query.edit_message_text(
        query.message.text_html + "\n\n❌ <b>Заявка отклонена.</b>",
        parse_mode=ParseMode.HTML
    )

# ── Helper ────────────────────────────────────────────────────────────────────

async def _reply(update: Update, text: str):
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(text, parse_mode=ParseMode.HTML)
