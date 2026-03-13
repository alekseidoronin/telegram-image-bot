"""
All conversation and command handlers.
"""

import asyncio
import logging
import threading
from io import BytesIO

from telegram import Update, LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ConversationHandler, ContextTypes, ApplicationHandlerStop
from telegram.error import TelegramError
import uuid
from payment_gateways import YooMoneyGateway, NowPaymentsGateway

import database
import image_service
import voice_service
import ui
import embedding_service
from config import (
    ASSEMBLYAI_KEY,
    GEMINI_API_KEY,
    ADMIN_URL,
    ADMIN_ID,
    DEFAULT_TOTAL_LIMIT,
    REQUIRED_CHANNEL,
    CHANNEL_LINK,
    CHANNEL_NAME,
    YOOMONEY_WALLET,
    YOOMONEY_SECRET,
    NOWPAYMENTS_API_KEY,
    NOWPAYMENTS_IPN_SECRET,
    ADMIN_URL,
    TEXT_MODEL,
    CHOOSE_MODE,
    CHOOSE_RATIO,
    CHOOSE_QUALITY,
    CHOOSE_SEARCH,
    AWAITING_PHOTO,
    AWAITING_MULTI_PHOTOS,
    AWAITING_PROMPT,
    CONFIRM_PROMPT,
    MODE_TXT2IMG,
    MODE_IMG2IMG,
    MODE_MULTI,
    MODE_LABELS,
    RATIO_PREFIX,
    QUALITY_PREFIX,
    ACTION_SEARCH_ON,
    ACTION_SEARCH_OFF,
    SET_MODEL_PREFIX,
    MAX_REFERENCE_IMAGES,
    MODEL_BANANA_PRO,
    CHOOSE_MODEL_TYPE,
)
from keyboards import (
    mode_keyboard,
    ratio_keyboard,
    quality_keyboard,
    search_keyboard,
    prompt_keyboard,
    generate_only_keyboard,
    done_photos_keyboard,
    language_keyboard,
    buy_keyboard,
    profile_keyboard,
    get_gateway_selection_keyboard,
    model_keyboard,
)
from i18n import t

logger = logging.getLogger(__name__)

async def notify_admin(context: ContextTypes.DEFAULT_TYPE, message: str):
    """Sends a notification message to the admin."""
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ <b>Системное уведомление:</b>\n{message}", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

# ── Force Sub Logic (Senior Implementation) ──────────────────────────────────

async def check_subscription(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """
    Checks if the user is subscribed to the required channel.
    Returns True if subscribed or if checking fails (safety bypass).
    """
    try:
        member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        if member.status in ['creator', 'administrator', 'member', 'restricted']:
            return True
        return False
    except TelegramError as e:
        logger.warning(f"Force Sub Warning (app.log): {e}. Passing user {user_id} by default.")
        return True

async def send_force_sub_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the required subscription message with buttons."""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(text='Подписаться на канал', url=CHANNEL_LINK)],
        [InlineKeyboardButton(text='✅ Я подписался', callback_data='check_force_sub')]
    ])
    text = (
        "Для всех новых пользователей доступно три генерации (4к фото стоит две генерации). "
        "Для использования бота необходимо подписаться на наш канал."
    )
    if update.message:
        await update.message.reply_text(text, reply_markup=kb)
    elif update.callback_query:
        # Use existing message if callback
        await update.callback_query.message.reply_text(text, reply_markup=kb)

async def verify_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback for 'I subscribed' button."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    is_subbed = await check_subscription(context, user_id)
    
    if not is_subbed:
        await query.answer('Вы еще не подписались на канал!', show_alert=True)
        return

    # Subscribed!
    await query.message.delete()
    # Log user and show menu
    user = update.effective_user
    await database.upsert_user(user.id, user.username, user.full_name)
    user_record = await database.get_user(user.id)
    lang = user_record['language'] if user_record else "ru"
    is_admin = await database.is_user_admin(user.id)
    
    legal_text = "\n\nПродолжая работу с ботом, вы принимаете условия <a href='https://neuronanobanana.duckdns.org/oferta'>Публичной оферты</a> и <a href='https://neuronanobanana.duckdns.org/privacy'>Политики конфиденциальности</a>."
    
    await query.message.reply_text(
        ui.welcome_text(lang) + legal_text,
        reply_markup=mode_keyboard(lang, is_admin=is_admin),
        parse_mode=ParseMode.HTML
    )
    await query.answer()


# ── Main Flow ────────────────────────────────────────────────────────────────


async def start(update, context):
    logger.info("Start command received from user %s", update.effective_user.id)
    user = update.effective_user
    
    # Force Sub Check
    if not await check_subscription(context, user.id):
        await send_force_sub_message(update, context)
        return

    # Deep Linking: request_web
    if context.args and "request_web" in context.args:
        from web_invite_handlers import webaccess_command
        return await webaccess_command(update, context)

    await database.upsert_user(user.id, user.username, user.full_name)
    user_record = await database.get_user(user.id)
    # Safer access to avoid IndexError if row_factory behavior is inconsistent
    try:
        user_dict = dict(user_record) if user_record else {}
        lang = user_dict.get("language", "ru")
        is_admin = (user_dict.get("telegram_id") == 632600126)
    except (TypeError, ValueError, AttributeError):
        lang = "ru"
    
    logger.info("User upserted to database")
    
    context.user_data.clear()
    context.user_data["lang"] = lang
    legal_text = "\n\nПродолжая работу с ботом, вы принимаете условия <a href='https://neuronanobanana.duckdns.org/oferta'>Публичной оферты</a> и <a href='https://neuronanobanana.duckdns.org/privacy'>Политики конфиденциальности</a>."
    text = ui.welcome_text(lang) + legal_text
    is_admin = await database.is_user_admin(user.id)
    markup = mode_keyboard(lang, is_admin=is_admin)
    if update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    return CHOOSE_MODE


async def go_menu(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    user_record = await database.get_user(user_id)
    
    try:
        user_dict = dict(user_record) if user_record else {}
        lang = user_dict.get("language", context.user_data.get("lang", "ru"))
        is_admin = (user_id == 632600126)
    except (TypeError, ValueError, AttributeError):
        lang = context.user_data.get("lang", "ru")
        is_admin = (user_id == 632600126)

    await query.answer()
    context.user_data.clear()
    context.user_data["lang"] = lang
    legal_text = "\n\nПродолжая работу с ботом, вы принимаете условия <a href='https://neuronanobanana.duckdns.org/oferta'>Публичной оферты</a> и <a href='https://neuronanobanana.duckdns.org/privacy'>Политики конфиденциальности</a>."
    await query.edit_message_text(
        ui.welcome_text(lang) + legal_text,
        reply_markup=mode_keyboard(lang, is_admin=is_admin),
        parse_mode=ParseMode.HTML
    )
    return CHOOSE_MODE


async def mode_chosen(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    
    # Check limit before proceeding to any menu
    user = await database.get_user(user_id)
    is_admin = await database.is_user_admin(user_id)
    balance = user['daily_limit'] if user else 0
    lang = context.user_data.get("lang", "ru")
    
    if not is_admin and balance < 1:
        await query.answer()
        # Reply with a new message with the buy buttons so they can purchase directly
        await query.message.reply_text(
            t("limit_exceeded", lang),
            reply_markup=buy_keyboard(lang)
        )
        return CHOOSE_MODE

    await query.answer()
    mode = query.data
    context.user_data["mode"] = mode
    lang = context.user_data.get("lang", "ru")
    await query.edit_message_text(
        ui.ratio_header(context),
        reply_markup=ratio_keyboard(lang),
        parse_mode=ParseMode.HTML
    )
    return CHOOSE_RATIO


async def ratio_chosen(update, context):
    query = update.callback_query
    await query.answer()
    ratio = query.data.replace(RATIO_PREFIX, "")
    context.user_data["aspect_ratio"] = ratio
    lang = context.user_data.get("lang", "ru")
    text = ui.quality_header(context) + "\n\n" + t("cost_warning", lang)
    await query.edit_message_text(
        text,
        reply_markup=quality_keyboard(lang),
        parse_mode=ParseMode.HTML
    )
    return CHOOSE_QUALITY


async def quality_chosen(update, context):
    query = update.callback_query
    await query.answer()
    quality = query.data.replace(QUALITY_PREFIX, "")
    context.user_data["quality"] = quality
    context.user_data["search"] = False
    mode = context.user_data.get("mode", MODE_TXT2IMG)
    lang = context.user_data.get("lang", "ru")

    if mode == MODE_IMG2IMG:
        await query.edit_message_text(ui.prompt_header(context), parse_mode=ParseMode.HTML)
        return AWAITING_PHOTO

    elif mode == MODE_MULTI:
        context.user_data["multi_images"] = []
        await query.edit_message_text(ui.prompt_header(context), parse_mode=ParseMode.HTML)
        await query.message.reply_text(
            ui.photo_count_text(0, lang),
            reply_markup=done_photos_keyboard(0, lang),
            parse_mode=ParseMode.HTML
        )
        return AWAITING_MULTI_PHOTOS

    else:
        await query.edit_message_text(ui.prompt_header(context), parse_mode=ParseMode.HTML)
        return AWAITING_PROMPT


async def search_chosen(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data["search"] = (query.data == ACTION_SEARCH_ON)
    mode = context.user_data.get("mode", MODE_TXT2IMG)
    lang = context.user_data.get("lang", "ru")

    if mode == MODE_IMG2IMG:
        await query.edit_message_text(ui.prompt_header(context), parse_mode=ParseMode.HTML)
        return AWAITING_PHOTO

    elif mode == MODE_MULTI:
        context.user_data["multi_images"] = []
        await query.edit_message_text(ui.prompt_header(context), parse_mode=ParseMode.HTML)
        await query.message.reply_text(
            ui.photo_count_text(0, lang),
            reply_markup=done_photos_keyboard(0, lang),
            parse_mode=ParseMode.HTML
        )
        return AWAITING_MULTI_PHOTOS

    else:
        await query.edit_message_text(ui.prompt_header(context), parse_mode=ParseMode.HTML)
        return AWAITING_PROMPT


# ── Photo Handlers ───────────────────────────────────────────────────────────


async def photo_received(update, context):
    user_id = update.effective_user.id
    if not await check_subscription(context, user_id):
        await send_force_sub_message(update, context)
        return AWAITING_PHOTO

    photo = update.message.photo[-1]
    file = await photo.get_file()
    buf = BytesIO()
    await file.download_to_memory(buf)
    buf.seek(0)
    context.user_data["input_image"] = buf.getvalue()
    lang = context.user_data.get("lang", "ru")
    await update.message.reply_text(
        "✅ Фото загружено\n\n"
        "✍️ Напиши или 🎤 надиктуй что нужно изменить." if lang == "ru" else
        "✅ Photo uploaded\n\n"
        "✍️ Write or 🎤 dictate what to change."
    )
    return AWAITING_PROMPT


async def multi_photo_received(update, context):
    user_id = update.effective_user.id
    if not await check_subscription(context, user_id):
        await send_force_sub_message(update, context)
        return AWAITING_MULTI_PHOTOS

    images = context.user_data.setdefault("multi_images", [])
    lang = context.user_data.get("lang", "ru")

    if len(images) >= MAX_REFERENCE_IMAGES:
        await update.message.reply_text(
            ui.photo_count_text(len(images), lang),
            reply_markup=done_photos_keyboard(len(images), lang),
        )
        return AWAITING_MULTI_PHOTOS

    photo = update.message.photo[-1]
    file = await photo.get_file()
    buf = BytesIO()
    await file.download_to_memory(buf)
    buf.seek(0)
    images.append(buf.getvalue())

    count = len(images)
    await update.message.reply_text(
        ui.photo_count_text(count, lang),
        reply_markup=done_photos_keyboard(count, lang),
    )
    return AWAITING_MULTI_PHOTOS


async def multi_photos_done(update, context):
    query = update.callback_query
    images = context.user_data.get("multi_images", [])
    lang = context.user_data.get("lang", "ru")
    if len(images) < 2:
        msg = "⚠️ Нужно минимум 2 фото!" if lang == "ru" else "⚠️ Need at least 2 photos!"
        await query.answer(msg, show_alert=True)
        return AWAITING_MULTI_PHOTOS
    await query.answer()
    text = (
        "✅ " + str(len(images)) + " фото загружено\n\n"
        "✍️ Напиши или 🎤 надиктуй что сделать с фото\n"
        "(объединить, микс, коллаж, наложить...)"
    ) if lang == "ru" else (
        "✅ " + str(len(images)) + " photos uploaded\n\n"
        "✍️ Write or 🎤 dictate what to do with them\n"
        "(blend, mix, collage, overlay...)"
    )
    await query.edit_message_text(text)
    return AWAITING_PROMPT


# ── Prompt Handlers ──────────────────────────────────────────────────────────


async def prompt_received(update, context):
    user_id = update.effective_user.id
    if not await check_subscription(context, user_id):
        await send_force_sub_message(update, context)
        return AWAITING_PROMPT

    prompt = update.message.text
    context.user_data["prompt"] = prompt
    lang = context.user_data.get("lang", "ru")
    msg = await update.message.reply_text(
        ui.prompt_confirm_text(prompt, context),
        reply_markup=prompt_keyboard(lang),
        parse_mode=ParseMode.HTML
    )
    context.user_data["confirm_msg_id"] = msg.message_id
    return CONFIRM_PROMPT

async def edited_prompt_received(update, context):
    if not update.edited_message or not update.edited_message.text: return CONFIRM_PROMPT
    prompt = update.edited_message.text
    context.user_data["prompt"] = prompt
    lang = context.user_data.get("lang", "ru")
    msg_id = context.user_data.get("confirm_msg_id")
    new_text = ui.prompt_confirm_text(prompt, context)
    
    if msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=update.edited_message.chat_id,
                message_id=msg_id,
                text=new_text,
                reply_markup=prompt_keyboard(lang),
                parse_mode=ParseMode.HTML
            )
            return CONFIRM_PROMPT
        except Exception:
            pass
            
    msg = await update.edited_message.reply_text(
        new_text,
        reply_markup=prompt_keyboard(lang),
        parse_mode=ParseMode.HTML
    )
    context.user_data["confirm_msg_id"] = msg.message_id
    return CONFIRM_PROMPT


async def voice_received(update, context):
    user_id = update.effective_user.id
    if not await check_subscription(context, user_id):
        await send_force_sub_message(update, context)
        return AWAITING_PROMPT

    lang = context.user_data.get("lang", "ru")
    api_key = await database.get_setting("ASSEMBLYAI_KEY")
    if not api_key:
        await update.message.reply_text(
            ui.error_text("API ключ AssemblyAI не настроен в дашборде." if lang == "ru" else "AssemblyAI API key is not configured in dashboard.", lang),
            parse_mode=ParseMode.HTML
        )
        return
    if not api_key:
        await update.message.reply_text(
            ui.error_text("Голосовые сообщения не настроены. Отправь текстом." if lang == "ru" else "Voice messages are not configured. Send text.", lang),
            parse_mode=ParseMode.HTML
        )
        return AWAITING_PROMPT

    status_txt = "🎤 Распознаю голос..." if lang == "ru" else "🎤 Recognizing voice..."
    status_msg = await update.message.reply_text(status_txt)

    voice = update.message.voice
    file = await voice.get_file()
    buf = BytesIO()
    await file.download_to_memory(buf)
    buf.seek(0)

    try:
        text = await voice_service.transcribe(api_key, buf.getvalue())
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        await notify_admin(context, f"Ошибка транскрибации у юзера <code>{update.effective_user.id}</code> (@{update.effective_user.username or '—'}):\n<code>{str(e)}</code>")
        text = None

    if not text:
        await status_msg.edit_text(
            ui.error_text(t("voice_error", lang), lang),
            parse_mode=ParseMode.HTML
        )
        return AWAITING_PROMPT

    await status_msg.delete()
    context.user_data["prompt"] = text
    msg = await update.message.reply_text(
        ui.prompt_confirm_text(text, context),
        reply_markup=prompt_keyboard(lang),
        parse_mode=ParseMode.HTML
    )
    context.user_data["confirm_msg_id"] = msg.message_id
    return CONFIRM_PROMPT


# ── Enhance / Generate ───────────────────────────────────────────────────────


async def enhance_prompt_handler(update, context):
    query = update.callback_query
    await query.answer()
    original = context.user_data.get("prompt", "")
    lang = context.user_data.get("lang", "ru")
    await query.edit_message_text(t("enhancing_prompt", lang))
    api_key = await database.get_setting("GEMINI_API_KEY")
    text_model = await database.get_setting("TEXT_MODEL")
    enhanced = await image_service.enhance_prompt(api_key, original, text_model=text_model)
    context.user_data["prompt"] = enhanced
    await query.edit_message_text(
        ui.enhanced_prompt_text(enhanced, lang),
        reply_markup=generate_only_keyboard(lang),
        parse_mode=ParseMode.HTML
    )
    return CONFIRM_PROMPT


async def generate_handler(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    
    # Global Interceptor: Force Sub
    if not await check_subscription(context, user_id):
        await send_force_sub_message(update, context)
        await query.answer()
        return ConversationHandler.END

    lang = context.user_data.get("lang", "ru")
    
    # Check block status
    if await database.is_user_blocked(user_id):
        await query.answer(t("blocked", lang), show_alert=True)
        return ConversationHandler.END

    # Check limits (balance)
    user = await database.get_user(user_id)
    is_admin = await database.is_user_admin(user_id)
    balance = user['daily_limit'] if user else 0
    
    quality = context.user_data.get("quality", "1K")
    cost_gens = 2 if quality == "4K" else 1

    if not is_admin and balance < cost_gens:
        await query.message.reply_text(
            t("limit_exceeded", lang),
            reply_markup=buy_keyboard(lang)
        )
        return CHOOSE_MODE

    await query.answer()

    mode = context.user_data.get("mode", MODE_TXT2IMG)
    prompt = context.user_data.get("prompt", "")
    ratio = context.user_data.get("aspect_ratio", "1:1")
    quality = context.user_data.get("quality", "1K")
    search = context.user_data.get("search", False)

    # Immediately remove buttons and show starting message
    try:
        await query.edit_message_text(t("start_generating", lang))
    except Exception:
        pass

    # Start progress bar (does not block threads)
    stop_event = asyncio.Event()
    progress_task = asyncio.create_task(
        ui.run_progress_bar(query.message, quality, stop_event, lang)
    )

    # Fetch settings from DB
    api_key = await database.get_setting("GEMINI_API_KEY")
    image_model = await database.get_setting("IMAGE_MODEL")
    text_model = await database.get_setting("TEXT_MODEL")

    # Generate
    result = None
    try:
        try:
            if mode == MODE_TXT2IMG:
                # Optional auto-enhance for short prompts
                if len(prompt) < 20:
                     prompt = await image_service.enhance_prompt(api_key, prompt, text_model=text_model)
                     context.user_data["prompt"] = prompt

                result = await image_service.text_to_image(
                    api_key, prompt, ratio, quality, search=search, image_model=image_model
                )
            elif mode == MODE_IMG2IMG:
                input_image = context.user_data.get("input_image")
                if input_image:
                    result = await image_service.image_to_image(
                        api_key, input_image, prompt, ratio, quality, search=search, image_model=image_model
                    )
            elif mode == MODE_MULTI:
                images_bytes = context.user_data.get("multi_images", [])
                if len(images_bytes) >= 2:
                    result = await image_service.multi_image(
                        api_key, images_bytes, prompt, ratio, quality, search=search, image_model=image_model
                    )
        except Exception as e:
            logger.error(f"Generation error: {e}")
            await notify_admin(context, f"Ошибка генерации у юзера <code>{user_id}</code> (@{query.from_user.username or '—'}):\nРежим: {mode}\nОшибка: <code>{str(e)}</code>")
            result = None
    finally:
        stop_event.set()
        await progress_task

    chat_id = query.message.chat_id
    caption = ui.settings_line(context)

    # Try to delete progress message
    try:
        await query.message.delete()
    except Exception:
        pass

    if result:
        bio = BytesIO(result)
        bio.name = "result.png"

        if quality == "4K" and len(result) > 5 * 1024 * 1024:
            await context.bot.send_document(
                chat_id=chat_id, document=bio, caption=caption,
            )
        else:
            try:
                await context.bot.send_photo(
                    chat_id=chat_id, photo=bio, caption=caption,
                )
            except Exception:
                bio.seek(0)
                compressed_txt = " (compression safe)" if lang == "en" else " (файл — Telegram сжимает фото)"
                await context.bot.send_document(
                    chat_id=chat_id, document=bio,
                    caption=caption + compressed_txt,
                )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=ui.error_text(t("generation_error", lang), lang),
            parse_mode=ParseMode.HTML
        )

    # Obtain embedding for the prompt (semantic memory)
    embedding = await embedding_service.get_embedding(prompt)

    # Log generation
    success_status = 1 if result else 0
    await database.log_generation(
        user_id, mode, quality, ratio, prompt, success=success_status, embedding=embedding
    )
    
    # Decrease balance if successful
    if success_status:
        await database.decrease_user_balance(user_id, amount=cost_gens)

    context.user_data.clear()
    return CHOOSE_MODE


# ── Wrong-State Hints ────────────────────────────────────────────────────────


async def photo_in_prompt_state(update, context):
    mode = context.user_data.get("mode", "")
    lang = context.user_data.get("lang", "ru")
    if mode == MODE_TXT2IMG:
        await update.message.reply_text(
            ui.error_text(t("expected_text", lang), lang),
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            ui.error_text(t("photo_already_loaded", lang), lang),
            parse_mode=ParseMode.HTML
        )
    return AWAITING_PROMPT


async def text_in_photo_state(update, context):
    lang = context.user_data.get("lang", "ru")
    await update.message.reply_text(
        ui.error_text(t("expected_photo", lang), lang),
        parse_mode=ParseMode.HTML
    )
    return AWAITING_PHOTO


async def voice_in_photo_state(update, context):
    lang = context.user_data.get("lang", "ru")
    await update.message.reply_text(
        ui.error_text(t("expected_photo_not_voice", lang), lang),
        parse_mode=ParseMode.HTML
    )
    return AWAITING_PHOTO


async def text_in_multi_photos(update, context):
    count = len(context.user_data.get("multi_images", []))
    lang = context.user_data.get("lang", "ru")
    await update.message.reply_text(
        ui.error_text(t("expected_images_not_text", lang), lang),
        reply_markup=done_photos_keyboard(count, lang),
        parse_mode=ParseMode.HTML
    )
    return AWAITING_MULTI_PHOTOS


async def voice_in_multi_photos(update, context):
    count = len(context.user_data.get("multi_images", []))
    lang = context.user_data.get("lang", "ru")
    await update.message.reply_text(
        ui.error_text(t("expected_images_not_voice", lang), lang),
        reply_markup=done_photos_keyboard(count, lang),
        parse_mode=ParseMode.HTML
    )
    return AWAITING_MULTI_PHOTOS


# ── Utility Commands ─────────────────────────────────────────────────────────


async def help_command(update, context):
    lang = context.user_data.get("lang", "ru")
    await update.message.reply_text(t("help_msg", lang))


async def admin_command(update, context):
    user_id = update.effective_user.id
    if not await database.is_user_admin(user_id):
        return
    
    stats = await database.get_stats()
    total_users = stats.get('total_users', 0)
    total_gens = stats.get('total_generations', 0)
    total_cost = stats.get('total_cost', 0.0)
    
    lang = context.user_data.get("lang", "ru")
    current_model = await database.get_setting("IMAGE_MODEL") or "gemini-3-pro-image-preview"
    
    text = t("admin_panel", lang, total_users=total_users, total_gens=total_gens, total_cost=total_cost)
    text += f"\n\n\ud83d\udd17 <b>Web Dashboard:</b> {ADMIN_URL}"
    text += f"\n\n\ud83c\udf4c <b>\u0422\u0435\u043a\u0443\u0449\u0430\u044f \u043c\u043e\u0434\u0435\u043b\u044c:</b> <code>{current_model}</code>"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("\ud83c\udf4c \u0421\u043c\u0435\u043d\u0438\u0442\u044c \u043c\u043e\u0434\u0435\u043b\u044c \u0433\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u0438", callback_data="admin_model_picker")],
        [InlineKeyboardButton("\ud83c\udf10 \u041e\u0442\u043a\u0440\u044b\u0442\u044c Web-\u043f\u0430\u043d\u0435\u043b\u044c", url=ADMIN_URL)],
    ])
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    elif update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def admin_model_picker_callback(update, context):
    """Show model selection keyboard to admin."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not await database.is_user_admin(user_id):
        return
    
    current_model = await database.get_setting("IMAGE_MODEL") or "gemini-3-pro-image-preview"
    lang = context.user_data.get("lang", "ru")
    
    await query.edit_message_text(
        "\ud83c\udf4c <b>\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043c\u043e\u0434\u0435\u043b\u044c \u0433\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u0438 \u0438\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\u0438\u0439:</b>\n"
        "<i>\u0418\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u0435 \u043f\u0440\u0438\u043c\u0435\u043d\u044f\u0435\u0442\u0441\u044f \u043c\u0433\u043d\u043e\u0432\u0435\u043d\u043d\u043e \u0434\u043b\u044f \u0432\u0441\u0435\u0445 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u0435\u0439.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=model_keyboard(current_model, lang)
    )


async def set_model_callback(update, context):
    """Save selected model to DB."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not await database.is_user_admin(user_id):
        return
    
    model_id = query.data[len(SET_MODEL_PREFIX):]
    from config import MODE_LABELS
    await database.set_setting("IMAGE_MODEL", model_id)
    
    model_labels = {
        "gemini-3-pro-image-preview":    "\ud83c\udf4c Nano Banana Pro",
        "gemini-3.1-flash-image-preview": "\u26a1 Nano Banana 2",
        "gemini-2.5-flash-image":         "\ud83c\udf3f Nano Banana",
    }
    label = model_labels.get(model_id, model_id)
    
    lang = context.user_data.get("lang", "ru")
    await query.edit_message_text(
        f"\u2705 <b>\u041c\u043e\u0434\u0435\u043b\u044c \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0430!</b>\n\n\u0410\u043a\u0442\u0438\u0432\u043d\u0430: {label}\n<code>{model_id}</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("\ud83d\udd04 \u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0435\u0449\u0451 \u0440\u0430\u0437", callback_data="admin_model_picker")],
            [InlineKeyboardButton("\u21a9\ufe0f \u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043c\u0435\u043d\u044e", callback_data="go_menu")],
        ])
    )

async def cancel(update, context):
    lang = context.user_data.get("lang", "ru")
    context.user_data.clear()
    context.user_data["lang"] = lang
    await update.message.reply_text(
        t("cancel_msg", lang) + "\n\n" + ("Выбери режим:" if lang == "ru" else "Choose a mode:"),
        reply_markup=mode_keyboard(lang),
    )
    return CHOOSE_MODE


async def language_command(update, context):
    lang = context.user_data.get("lang", "ru")
    markup = language_keyboard(lang)
    text = t("select_lang", lang)
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(text, reply_markup=markup)
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup)


async def profile_callback(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = await database.get_user(user_id)
    lang = context.user_data.get("lang", "ru")
    
    limit = user['daily_limit'] if user else 0
    limit_str = "∞ (Unlimited)" if limit == -1 else str(limit)
    
    if lang == "ru":
        limit_str = "♾ Безлимитно" if limit == -1 else str(limit)
        text = (
            f"💼 <b>Мой профиль</b>\n\n"
            f"👤 ID: <code>{user_id}</code>\n"
            f"💎 Остаток генераций: <b>{limit_str}</b>\n\n"
            f"<i>Примечание: генерация 4K (высокое качество) стоит 2 кредита.</i>"
        )
    else:
        text = (
            f"💼 <b>My Profile</b>\n\n"
            f"👤 ID: <code>{user_id}</code>\n"
            f"💎 Remaining generations: <b>{limit_str}</b>\n\n"
            f"<i>Note: 4K (high quality) generation costs 2 credits.</i>"
        )
        
    await query.edit_message_text(text, reply_markup=profile_keyboard(lang), parse_mode=ParseMode.HTML)
    return CHOOSE_MODE

async def balance_command(update, context):
    user_id = update.effective_user.id
    user = await database.get_user(user_id)
    lang = context.user_data.get("lang", "ru")
    
    limit = user['daily_limit'] if user else 0
    limit_str = "♾ Безлимитно" if limit == -1 else str(limit)
    
    if lang == "ru":
        text = (
            f"💼 <b>Мой профиль</b>\n\n"
            f"👤 ID: <code>{user_id}</code>\n"
            f"💎 Остаток генераций: <b>{limit_str}</b>\n\n"
            f"<i>Примечание: генерация 4K (высокое качество) стоит 2 кредита.</i>"
        )
    else:
        limit_str = "∞ Unlimited" if limit == -1 else str(limit)
        text = (
            f"💼 <b>My Profile</b>\n\n"
            f"👤 ID: <code>{user_id}</code>\n"
            f"💎 Remaining generations: <b>{limit_str}</b>\n\n"
            f"<i>Note: 4K (high quality) generation costs 2 credits.</i>"
        )
        
    await update.message.reply_text(text, reply_markup=profile_keyboard(lang), parse_mode=ParseMode.HTML)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Experimental semantic search command.
    Usage: /search [query]
    """
    user_id = update.effective_user.id
    lang = context.user_data.get("lang", "ru")
    
    if not context.args:
        hint = "💡 Пожалуйста, напишите что искать после команды.\nПример: `/search киберпанк город`" if lang == "ru" else "💡 Please provide a search query.\nExample: `/search cyberpunk city`"
        await update.message.reply_text(hint, parse_mode=ParseMode.MARKDOWN)
        return
        
    query_text = " ".join(context.args)
    status_msg = await update.message.reply_text("🔍 " + ("Ищу в вашей истории..." if lang == "ru" else "Searching your history..."))
    
    query_embedding = await embedding_service.get_embedding(query_text)
    if not query_embedding:
        await status_msg.edit_text("❌ " + ("Не удалось обработать запрос." if lang == "ru" else "Failed to process request."))
        return
        
    results = await database.search_similar_generations(user_id, query_embedding, limit=5)
    
    if not results:
        await status_msg.edit_text("🤷 " + ("Похожих генераций не найдено." if lang == "ru" else "No similar generations found."))
        return
        
    response = "🎯 <b>" + ("Найденные совпадения:" if lang == "ru" else "Matches found:") + "</b>\n\n"
    for i, res in enumerate(results, 1):
        sim_pct = min(100, int(res['similarity'] * 100))
        # Highlight matches with > 60% similarity
        if sim_pct < 40: continue
        response += f"{i}. «<i>{res['prompt'][:100]}...</i>»\n   📊 " + ("Сходство" if lang == "ru" else "Similarity") + f": {sim_pct}%\n\n"
        
    if response == "🎯 <b>" + ("Найденные совпадения:" if lang == "ru" else "Matches found:") + "</b>\n\n":
        await status_msg.edit_text("🤷 " + ("Ничего достаточно похожего не найдено." if lang == "ru" else "No relevant items found."))
    else:
        await status_msg.edit_text(response, parse_mode=ParseMode.HTML)

async def buy_menu_callback(update, context):
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("lang", "ru")
    await query.edit_message_text(t("buy_title", lang), reply_markup=buy_keyboard(lang))
    return CHOOSE_MODE

async def buy_command(update, context):
    lang = context.user_data.get("lang", "ru")
    await update.message.reply_text(t("buy_title", lang), reply_markup=buy_keyboard(lang))

async def paysupport_command(update, context):
    lang = context.user_data.get("lang", "ru")
    await update.message.reply_text(t("paysupport_msg", lang))

async def select_package_callback(update, context):
    query = update.callback_query
    await query.answer()
    
    # Format: select_package_{id}_{amount}_{price_rub}
    parts = query.data.split("_")
    if len(parts) < 5:
        return
        
    package_id = parts[2]
    amount = parts[3]
    price_rub = parts[4]
    
    # Calculate stars price (roughly matches our stars_map)
    stars_map = {"1": 14, "10": 87, "50": 347, "100": 608}
    stars_price = stars_map.get(package_id, int(amount) * 14)
    
    lang = context.user_data.get("lang", "ru")
    if lang == "ru":
        text = (
            f"📦 <b>Пакет: {amount} генераций</b>\n"
            f"💰 <b>Стоимость: {price_rub}₽</b>\n\n"
            f"Пожалуйста, выберите удобный способ оплаты:"
        )
    else:
        text = (
            f"📦 <b>Package: {amount} generations</b>\n"
            f"💰 <b>Price: {price_rub} RUB</b>\n\n"
            f"Please choose a payment method:"
        )
        
    await query.edit_message_text(
        text, 
        reply_markup=get_gateway_selection_keyboard(package_id, price_rub, stars_price),
        parse_mode=ParseMode.HTML
    )
    return CHOOSE_MODE

async def buy_gateway_callback(update, context):
    query = update.callback_query
    await query.answer()
    
    # Format: buy_{gateway}_{package_id}
    parts = query.data.split("_")
    if len(parts) < 3:
        return
        
    gateway_name = parts[1]
    package_id = parts[2]
    generations = int(package_id)
    
    # Calculate amount
    price_map = {1: 15, 10: 100, 50: 400, 100: 700}
    amount = price_map.get(generations, generations * 15)
    
    user_id = update.effective_user.id
    order_id = str(uuid.uuid4())
    lang = context.user_data.get("lang", "ru")
    description = f"Пополнение баланса ({generations} ген.)" if lang == "ru" else f"Balance top-up ({generations} gens)"
    
    if gateway_name == "stars":
        return await buy_stars_invoice(update, context, generations)
        
    payment_url = None
    if gateway_name == "yoomoney":
        wallet = await database.get_setting("YOOMONEY_WALLET") or YOOMONEY_WALLET
        secret = await database.get_setting("YOOMONEY_SECRET") or YOOMONEY_SECRET
        
        if not wallet:
            await query.message.reply_text("YooMoney не настроен (receiver wallet missing).")
            return CHOOSE_MODE
            
        gw = YooMoneyGateway(wallet, secret, success_url=f"https://t.me/{(await context.bot.get_me()).username}")
        payment_url = gw.generate_payment_url(order_id, amount, description)
        
    elif gateway_name == "crypto":
        api_key = await database.get_setting("NOWPAYMENTS_API_KEY") or NOWPAYMENTS_API_KEY
        ipn_secret = await database.get_setting("NOWPAYMENTS_IPN_SECRET") or NOWPAYMENTS_IPN_SECRET
        
        if not api_key:
            await query.message.reply_text("NOWPayments не настроен (API key missing).")
            return CHOOSE_MODE
            
        gw = NowPaymentsGateway(api_key, ipn_secret)
        callback_url = f"{ADMIN_URL}/api/webhooks/nowpayments"
        payment_url = gw.create_invoice(
            order_id=order_id,
            amount=amount,
            currency='rub',
            description=description,
            callback_url=callback_url
        )

    if not payment_url:
        await query.message.reply_text(t("buy_error", lang))
        return CHOOSE_MODE

    # Create pending transaction
    await database.create_transaction(order_id, user_id, amount, generations, gateway_name)
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Оплатить по ссылке", url=payment_url)],
        [InlineKeyboardButton(t("payment_i_paid", lang), callback_data=f"paid_done:{order_id}")],
    ])
    await query.message.reply_text(
        f"Ваш заказ <code>{order_id}</code> создан.\nСумма: <b>{amount} руб.</b>\n\n{t('payment_after_pay', lang)}",
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )
    return CHOOSE_MODE

async def buy_stars_invoice(update, context, generations):
    query = update.callback_query
    price_map = {1: 14, 10: 87, 50: 347, 100: 608}
    stars = price_map.get(generations, generations * 14)
    
    lang = context.user_data.get("lang", "ru")
    user_id = query.from_user.id
    order_id = "stars-" + str(uuid.uuid4())[:8]
    
    # Create pending transaction
    await database.create_transaction(order_id, user_id, float(stars), generations, "stars")
    
    title = f"{generations} Generation(s)" if lang == "en" else f"{generations} Генераций"
    description = f"Buy {generations} generations for {stars} Telegram Stars." if lang == "en" else f"Покупка {generations} генераций за {stars} Telegram Stars."
    payload = f"buy_{generations}_{order_id}"
    
    prices = [LabeledPrice(title, int(stars))]
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💳 {t('btn_generate', lang)}", pay=True)],
        [InlineKeyboardButton(t("payment_i_paid", lang), callback_data=f"paid_done:{order_id}")],
    ])
    
    try:
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title=title,
            description=description,
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=prices,
            reply_markup=kb
        )
    except Exception as e:
        logger.error(f"Invoice error: {e}")
        await query.message.reply_text(t("buy_error", (context.user_data.get("lang", "ru"))))
        
    return CHOOSE_MODE

async def precheckout_callback(update, context):
    query = update.pre_checkout_query
    if query.invoice_payload.startswith("buy_"):
        await query.answer(ok=True)
    else:
        lang = context.user_data.get("lang", "ru")
        await query.answer(ok=False, error_message=t("buy_error", lang))

async def successful_payment_callback(update, context):
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    telegram_id = update.message.chat_id

    # Log raw payment data for debugging
    logger.info(
        "STARS PAYMENT: user=%s currency=%s amount=%s payload=%s "
        "provider_charge=%s telegram_charge=%s",
        telegram_id,
        payment.currency,
        payment.total_amount,
        payload,
        payment.provider_payment_charge_id,
        payment.telegram_payment_charge_id,
    )

    if not payload.startswith("buy_"):
        logger.warning("Unknown payment payload: %s", payload)
        return

    if payment.currency != "XTR":
        logger.error("Unexpected currency %s for Stars payment", payment.currency)
        return

    parts = payload.split("_")
    generations = int(parts[1])
    stars = payment.total_amount
    charge_id = payment.telegram_payment_charge_id

    # If payload contains order_id, use it, else generate
    if len(parts) > 2:
        order_id = parts[2]
    else:
        order_id = "stars-" + str(uuid.uuid4())[:8]

    # Duplicate check by charge_id
    existing = await database.get_transaction(order_id)
    if existing and existing["status"] == "paid":
        logger.warning("Duplicate Stars payment ignored: %s", charge_id)
        lang = context.user_data.get("lang", "ru")
        await update.message.reply_text(t("buy_success", lang, generations=generations))
        return

    # Step 1: Record in transactions table
    try:
        await database.create_transaction(
            order_id=order_id,
            user_id=telegram_id,
            amount=float(stars),
            generations=generations,
            gateway="stars",
        )
    except Exception as e:
        logger.error("Failed to create Stars transaction record: %s", e)

    # Step 2: Mark as paid and credit balance
    await database.complete_transaction(order_id)

    # Step 3: Also log in payments table (legacy)
    try:
        await database.log_payment(telegram_id, stars, generations, charge_id)
    except Exception as e:
        logger.error("Failed to log Stars payment: %s", e)

    # Step 4: Notify user
    lang = context.user_data.get("lang", "ru")
    await update.message.reply_text(t("buy_success", lang, generations=generations))

    # Step 5: Notify admin (Stars)
    try:
        user = update.effective_user
        price_amount = payment.total_amount
        price_currency = payment.currency  # XTR
        user_info = f"{user.full_name} (@{user.username or '—'}, ID {user.id})"

        admin_text = (
            "💰 <b>Оплата подтверждена!</b>\n"
            f"Сумма: <b>{price_amount} {price_currency}</b>\n"
            f"Пакет: <b>{generations} ген.</b>\n"
            f"Юзер: {user_info}\n"
            f"Order ID: <code>{order_id}</code>"
        )

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Failed to send Stars admin notification: {e}")

async def open_model_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = context.user_data.get("lang", "ru")
    await query.edit_message_text(ui.model_header(context), reply_markup=model_keyboard(lang), parse_mode=ParseMode.HTML)
    return CHOOSE_MODEL_TYPE

async def set_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # setmod_model_id
    model_id = query.data[len(SET_MODEL_PREFIX):]
    context.user_data["image_model"] = model_id
    
    # Notify user
    lang = context.user_data.get("lang", "ru")
    from config import MODEL_LABELS_GEN
    mod_name = MODEL_LABELS_GEN.get(model_id, model_id)
    
    await query.answer(f"Модель изменена на {mod_name}" if lang == "ru" else f"Model changed to {mod_name}")
    
    # Return to profile or menu? Let's go to profile to see the change
    user_id = query.from_user.id
    user_record = await database.get_user(user_id)
    limit = user_record['daily_limit'] if user_record else 0
    
    limit_str = "∞ Безлимит" if limit == -1 else str(limit)
    if lang == "ru":
        text = (
            f"💼 <b>Мой профиль</b>\n\n"
            f"👤 ID: <code>{user_id}</code>\n"
            f"💎 Остаток генераций: <b>{limit_str}</b>\n\n"
            f"🤖 Текущая модель: <b>{mod_name}</b>\n\n"
            f"<i>Примечание: генерация 4K (высокое качество) стоит 2 кредита.</i>"
        )
    else:
        limit_str = "∞ Unlimited" if limit == -1 else str(limit)
        text = (
            f"💼 <b>My Profile</b>\n\n"
            f"👤 ID: <code>{user_id}</code>\n"
            f"💎 Remaining generations: <b>{limit_str}</b>\n\n"
            f"🤖 Current model: <b>{mod_name}</b>\n\n"
            f"<i>Note: 4K (high quality) generation costs 2 credits.</i>"
        )
    
    await query.edit_message_text(text, reply_markup=profile_keyboard(lang), parse_mode=ParseMode.HTML)
    return CHOOSE_MODE


async def set_language_callback(update, context):
    query = update.callback_query
    user_id = update.effective_user.id
    
    # "answer" to clear loading state in some clients
    await query.answer()
    
    # Extract language from callback data (e.g. setlang_ru -> ru)
    lang = query.data.split("_")[1]
    
    # 1. Update Session and Database
    context.user_data["lang"] = lang
    await database.set_user_language(user_id, lang)
    
    # 2. Show confirmation message
    await query.edit_message_text(t("lang_changed", lang))
    
    # 3. Automatically send the main menu in the NEW language
    is_admin = await database.is_user_admin(user_id)
    text = ui.welcome_text(lang)
    markup = mode_keyboard(lang, is_admin=is_admin)
    
    # Send as a NEW message so it's clear the state changed
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=markup,
        parse_mode=ParseMode.HTML
    )
    return CHOOSE_MODE


async def error_handler(update, context):
    logger.error(msg="Exception while handling update:", exc_info=context.error)
    # Notify admin about critical errors
    err_str = str(context.error)
    if any(q in err_str.lower() for q in ["rate limit", "quota", "exhausted", "api key", "connection"]):
        await notify_admin(context, f"Критическая ошибка в работе бота:\n<code>{err_str}</code>")


async def global_trace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("RECEIVED UPDATE: %s", update.to_dict())


# ── YooMoney Payment Confirmation Flow ────────────────────────────────────────

_payment_notified = {}  # order_id -> timestamp, throttle duplicate clicks

async def payment_done_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User clicked I have paid button after YooMoney payment."""
    query = update.callback_query
    await query.answer()

    order_id = query.data.split(":", 1)[1] if ":" in query.data else ""
    if not order_id:
        return

    lang = context.user_data.get("lang", "ru")
    user_id = update.effective_user.id

    # Fetch transaction
    tx = await database.get_transaction(order_id)
    if not tx:
        await query.answer(t("buy_error", lang), show_alert=True)
        return
    if tx["user_id"] != user_id:
        await query.answer(t("buy_error", lang), show_alert=True)
        return
    if tx["status"] == "paid":
        await query.answer(t("payment_confirmed_user", lang, generations=tx["generations"]), show_alert=True)
        return

    # Throttle: one notification per order per 60 seconds
    import time
    now = time.time()
    last = _payment_notified.get(order_id, 0)
    if now - last < 60:
        await query.answer(t("payment_already_sent", lang), show_alert=True)
        return
    _payment_notified[order_id] = now

    # Send notification to admin
    user = update.effective_user
    admin_text = (
        f"💳 <b>Запрос подтверждения оплаты</b>\n\n"
        f"👤 Пользователь: {user.full_name} (@{user.username or 'N/A'})\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📦 Заказ: <code>{order_id}</code>\n"
        f"💰 Сумма: {tx['amount']} руб.\n"
        f"🎯 Генераций: {tx['generations']}\n"
        f"🔌 Шлюз: {tx['gateway']}\n\n"
        f"Подтвердите, если оплата получена:"
    )
    admin_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"adm_confirm:{order_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"adm_reject:{order_id}"),
        ]
    ])
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            reply_markup=admin_kb,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Failed to notify admin about payment: {e}")

    # Update user message — remove "I paid" button, show waiting text
    try:
        await query.edit_message_text(
            f"Ваш заказ <code>{order_id}</code>\n{t(payment_notify_sent, lang)}",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


async def admin_confirm_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin confirms a YooMoney payment."""
    query = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await query.answer("Нет доступа", show_alert=True)
        return
    await query.answer()

    order_id = query.data.split(":", 1)[1] if ":" in query.data else ""
    if not order_id:
        return

    tx = await database.get_transaction(order_id)
    if not tx:
        await query.edit_message_text("Заказ не найден.")
        return
    if tx["status"] == "paid":
        await query.edit_message_text(f"Заказ <code>{order_id}</code> уже подтверждён ранее.", parse_mode=ParseMode.HTML)
        return

    # Complete transaction — mark paid + add balance
    success = await database.complete_transaction(order_id)
    if not success:
        await query.edit_message_text(f"Не удалось подтвердить заказ <code>{order_id}</code>.", parse_mode=ParseMode.HTML)
        return

    # Update admin message
    await query.edit_message_text(
        f"✅ Заказ <code>{order_id}</code> подтверждён.\n+{tx['generations']} генераций для пользователя {tx['user_id']}.",
        parse_mode=ParseMode.HTML,
    )

    # Notify user
    try:
        user_record = await database.get_user(tx["user_id"])
        lang = user_record["language"] if user_record else "ru"
        await context.bot.send_message(
            chat_id=tx["user_id"],
            text=t("payment_confirmed_user", lang, generations=tx["generations"]),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Failed to notify user about confirmed payment: {e}")


async def admin_reject_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin rejects a YooMoney payment."""
    query = update.callback_query
    if update.effective_user.id != ADMIN_ID:
        await query.answer("Нет доступа", show_alert=True)
        return
    await query.answer()

    order_id = query.data.split(":", 1)[1] if ":" in query.data else ""
    if not order_id:
        return

    tx = await database.get_transaction(order_id)
    if not tx:
        await query.edit_message_text("Заказ не найден.")
        return
    if tx["status"] != "pending":
        await query.edit_message_text(f"Заказ <code>{order_id}</code> уже обработан (статус: {tx['status']}).", parse_mode=ParseMode.HTML)
        return

    await database.reject_transaction(order_id)

    await query.edit_message_text(
        f"❌ Заказ <code>{order_id}</code> отклонён.",
        parse_mode=ParseMode.HTML,
    )

    # Notify user
    try:
        user_record = await database.get_user(tx["user_id"])
        lang = user_record["language"] if user_record else "ru"
        await context.bot.send_message(
            chat_id=tx["user_id"],
            text=t("payment_rejected_user", lang),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Failed to notify user about rejected payment: {e}")
