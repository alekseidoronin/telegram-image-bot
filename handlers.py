"""
All conversation and command handlers.
"""

import asyncio
import logging
import threading
from io import BytesIO

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ConversationHandler, ContextTypes

import database
import image_service
import voice_service
import ui
from config import (
    ASSEMBLYAI_KEY,
    GEMINI_API_KEY,
    ADMIN_URL,
    DEFAULT_TOTAL_LIMIT,
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
    MAX_REFERENCE_IMAGES,
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
)
from i18n import t

logger = logging.getLogger(__name__)


# ── Main Flow ────────────────────────────────────────────────────────────────


async def start(update, context):
    logger.info("Start command received from user %s", update.effective_user.id)
    user = update.effective_user
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
    text = ui.welcome_text(lang)
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
    await query.edit_message_text(
        ui.welcome_text(lang),
        reply_markup=mode_keyboard(lang, is_admin=is_admin),
        parse_mode=ParseMode.HTML
    )
    return CHOOSE_MODE


async def mode_chosen(update, context):
    query = update.callback_query
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
    await query.edit_message_text(
        ui.quality_header(context),
        reply_markup=quality_keyboard(lang),
        parse_mode=ParseMode.HTML
    )
    return CHOOSE_QUALITY


async def quality_chosen(update, context):
    query = update.callback_query
    await query.answer()
    quality = query.data.replace(QUALITY_PREFIX, "")
    context.user_data["quality"] = quality
    lang = context.user_data.get("lang", "ru")
    await query.edit_message_text(
        ui.search_header(context),
        reply_markup=search_keyboard(lang),
        parse_mode=ParseMode.HTML
    )
    return CHOOSE_SEARCH


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
    prompt = update.message.text
    context.user_data["prompt"] = prompt
    lang = context.user_data.get("lang", "ru")
    await update.message.reply_text(
        ui.prompt_confirm_text(prompt, context),
        reply_markup=prompt_keyboard(lang),
        parse_mode=ParseMode.HTML
    )
    return CONFIRM_PROMPT


async def voice_received(update, context):
    lang = context.user_data.get("lang", "ru")
    if not ASSEMBLYAI_KEY:
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

    text = await voice_service.transcribe(ASSEMBLYAI_KEY, buf.getvalue())

    if not text:
        await status_msg.edit_text(
            ui.error_text(t("voice_error", lang), lang),
            parse_mode=ParseMode.HTML
        )
        return AWAITING_PROMPT

    await status_msg.delete()
    context.user_data["prompt"] = text
    await update.message.reply_text(
        ui.prompt_confirm_text(text, context),
        reply_markup=prompt_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return CONFIRM_PROMPT


# ── Enhance / Generate ───────────────────────────────────────────────────────


async def enhance_prompt_handler(update, context):
    query = update.callback_query
    await query.answer()
    original = context.user_data.get("prompt", "")
    lang = context.user_data.get("lang", "ru")
    await query.edit_message_text(t("enhancing_prompt", lang))
    enhanced = await image_service.enhance_prompt(GEMINI_API_KEY, original)
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
    lang = context.user_data.get("lang", "ru")
    
    # Check block status
    if await database.is_user_blocked(user_id):
        await query.answer(t("blocked", lang), show_alert=True)
        return ConversationHandler.END

    # Check limits
    user = await database.get_user(user_id)
    is_admin = await database.is_user_admin(user_id)
    limit = user['daily_limit'] if user else DEFAULT_TOTAL_LIMIT
    usage = await database.get_user_total_count(user_id)
    
    if not is_admin and usage >= limit:
        await query.answer(t("limit_exceeded", lang), show_alert=True)
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

    # Generate
    result = None
    try:
        if mode == MODE_TXT2IMG:
            result = await image_service.text_to_image(
                GEMINI_API_KEY, prompt, ratio, quality, search=search,
            )
        elif mode == MODE_IMG2IMG:
            input_image = context.user_data.get("input_image")
            if input_image:
                result = await image_service.image_to_image(
                    GEMINI_API_KEY, input_image, prompt, ratio, quality, search=search,
                )
        elif mode == MODE_MULTI:
            images_bytes = context.user_data.get("multi_images", [])
            if len(images_bytes) >= 2:
                result = await image_service.multi_image(
                    GEMINI_API_KEY, images_bytes, prompt, ratio, quality, search=search,
                )
    finally:
        stop_event.set()
        await progress_task

    chat_id = query.message.chat_id
    caption = ui.settings_line(context)

    # Try to update progress message to "Done"
    done_text = t("msg_done", lang)
    try:
        await query.message.edit_text(done_text)
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

    # Log generation
    await database.log_generation(
        user_id, mode, quality, ratio, prompt, success=(1 if result else 0)
    )

    # RESTART LOGIC: Instead of clearing everything, we go back to menu
    # But we want to allow user to generate again with same settings OR choose new mode
    await context.bot.send_message(
        chat_id=chat_id,
        text=t("msg_what_next", lang),
        reply_markup=mode_keyboard(lang),
    )
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
    text = t("admin_panel", lang, total_users=total_users, total_gens=total_gens, total_cost=total_cost)
    text += f"\n\n🔗 <b>Web Dashboard:</b> {ADMIN_URL}"
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(text, parse_mode=ParseMode.HTML)
    elif update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


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


async def global_trace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("RECEIVED UPDATE: %s", update.to_dict())
