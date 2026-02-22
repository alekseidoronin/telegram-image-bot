"""
All conversation and command handlers.
"""

import asyncio
import logging
import threading
from io import BytesIO

from telegram import Update
from telegram.ext import ConversationHandler, ContextTypes

import database
import image_service
import voice_service
import ui
from config import (
    ASSEMBLYAI_KEY,
    GEMINI_API_KEY,
    DEFAULT_DAILY_LIMIT,
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
)

logger = logging.getLogger(__name__)


# ── Main Flow ────────────────────────────────────────────────────────────────


async def start(update, context):
    logger.info("Start command received from user %s", update.effective_user.id)
    user = update.effective_user
    await database.upsert_user(user.id, user.username, user.full_name)
    logger.info("User upserted to database")
    
    context.user_data.clear()
    text = ui.welcome_text()
    if update.message:
        await update.message.reply_text(text, reply_markup=mode_keyboard())
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=mode_keyboard())
    return CHOOSE_MODE


async def go_menu(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(ui.welcome_text(), reply_markup=mode_keyboard())
    return CHOOSE_MODE


async def mode_chosen(update, context):
    query = update.callback_query
    await query.answer()
    mode = query.data
    context.user_data["mode"] = mode
    await query.edit_message_text(
        ui.ratio_header(context),
        reply_markup=ratio_keyboard(),
    )
    return CHOOSE_RATIO


async def ratio_chosen(update, context):
    query = update.callback_query
    await query.answer()
    ratio = query.data.replace(RATIO_PREFIX, "")
    context.user_data["aspect_ratio"] = ratio
    await query.edit_message_text(
        ui.quality_header(context),
        reply_markup=quality_keyboard(),
    )
    return CHOOSE_QUALITY


async def quality_chosen(update, context):
    query = update.callback_query
    await query.answer()
    quality = query.data.replace(QUALITY_PREFIX, "")
    context.user_data["quality"] = quality
    await query.edit_message_text(
        ui.search_header(context),
        reply_markup=search_keyboard(),
    )
    return CHOOSE_SEARCH


async def search_chosen(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data["search"] = (query.data == ACTION_SEARCH_ON)
    mode = context.user_data.get("mode", MODE_TXT2IMG)

    if mode == MODE_IMG2IMG:
        await query.edit_message_text(ui.prompt_header(context))
        return AWAITING_PHOTO

    elif mode == MODE_MULTI:
        context.user_data["multi_images"] = []
        await query.edit_message_text(ui.prompt_header(context))
        await query.message.reply_text(
            ui.photo_count_text(0),
            reply_markup=done_photos_keyboard(0),
        )
        return AWAITING_MULTI_PHOTOS

    else:
        await query.edit_message_text(ui.prompt_header(context))
        return AWAITING_PROMPT


# ── Photo Handlers ───────────────────────────────────────────────────────────


async def photo_received(update, context):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    buf = BytesIO()
    await file.download_to_memory(buf)
    buf.seek(0)
    context.user_data["input_image"] = buf.getvalue()
    await update.message.reply_text(
        "✅ Фото загружено\n\n"
        "✍️ Напиши или 🎤 надиктуй что нужно изменить."
    )
    return AWAITING_PROMPT


async def multi_photo_received(update, context):
    images = context.user_data.setdefault("multi_images", [])

    if len(images) >= MAX_REFERENCE_IMAGES:
        await update.message.reply_text(
            ui.photo_count_text(len(images)),
            reply_markup=done_photos_keyboard(len(images)),
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
        ui.photo_count_text(count),
        reply_markup=done_photos_keyboard(count),
    )
    return AWAITING_MULTI_PHOTOS


async def multi_photos_done(update, context):
    query = update.callback_query
    images = context.user_data.get("multi_images", [])
    if len(images) < 2:
        await query.answer("⚠️ Нужно минимум 2 фото!", show_alert=True)
        return AWAITING_MULTI_PHOTOS
    await query.answer()
    await query.edit_message_text(
        "✅ " + str(len(images)) + " фото загружено\n\n"
        "✍️ Напиши или 🎤 надиктуй что сделать с фото\n"
        "(объединить, микс, коллаж, наложить...)"
    )
    return AWAITING_PROMPT


# ── Prompt Handlers ──────────────────────────────────────────────────────────


async def prompt_received(update, context):
    prompt = update.message.text
    context.user_data["prompt"] = prompt
    await update.message.reply_text(
        ui.prompt_confirm_text(prompt, context),
        reply_markup=prompt_keyboard(),
    )
    return CONFIRM_PROMPT


async def voice_received(update, context):
    if not ASSEMBLYAI_KEY:
        await update.message.reply_text(
            ui.error_text("Голосовые сообщения не настроены. Отправь текстом.")
        )
        return AWAITING_PROMPT

    status_msg = await update.message.reply_text("🎤 Распознаю голос...")

    voice = update.message.voice
    file = await voice.get_file()
    buf = BytesIO()
    await file.download_to_memory(buf)
    buf.seek(0)

    text = await voice_service.transcribe(ASSEMBLYAI_KEY, buf.getvalue())

    if not text:
        await status_msg.edit_text(
            ui.error_text("Не удалось распознать. Попробуй ещё раз или отправь текстом.")
        )
        return AWAITING_PROMPT

    await status_msg.delete()
    context.user_data["prompt"] = text
    await update.message.reply_text(
        ui.prompt_confirm_text(text, context),
        reply_markup=prompt_keyboard(),
    )
    return CONFIRM_PROMPT


# ── Enhance / Generate ───────────────────────────────────────────────────────


async def enhance_prompt_handler(update, context):
    query = update.callback_query
    await query.answer()
    original = context.user_data.get("prompt", "")
    await query.edit_message_text("✨ Улучшаю промпт...")
    enhanced = await image_service.enhance_prompt(GEMINI_API_KEY, original)
    context.user_data["prompt"] = enhanced
    await query.edit_message_text(
        ui.enhanced_prompt_text(enhanced),
        reply_markup=generate_only_keyboard(),
    )
    return CONFIRM_PROMPT


async def generate_handler(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    
    # Check block status
    if await database.is_user_blocked(user_id):
        await query.answer("Вы заблокированы.", show_alert=True)
        return ConversationHandler.END

    # Check limits
    user = await database.get_user(user_id)
    limit = user['daily_limit'] if user else DEFAULT_DAILY_LIMIT
    usage = await database.get_user_today_count(user_id)
    
    if usage >= limit:
        await query.answer(f"Лимит исчерпан ({limit}/{limit}). Попробуй завтра!", show_alert=True)
        return CHOOSE_MODE

    await query.answer()

    mode = context.user_data.get("mode", MODE_TXT2IMG)
    prompt = context.user_data.get("prompt", "")
    ratio = context.user_data.get("aspect_ratio", "1:1")
    quality = context.user_data.get("quality", "1K")
    search = context.user_data.get("search", False)

    # Immediately remove buttons and show starting message
    try:
        await query.edit_message_text("⏳ Запускаю генерацию...")
    except Exception:
        pass

    # Start progress bar (does not block threads)
    stop_event = asyncio.Event()
    progress_task = asyncio.create_task(
        ui.run_progress_bar(query.message, quality, stop_event)
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
    try:
        await query.message.edit_text("✅ Готово!")
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
                await context.bot.send_document(
                    chat_id=chat_id, document=bio,
                    caption=caption + " (файл — Telegram сжимает фото)",
                )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=ui.error_text("Не удалось сгенерировать. Попробуй другой промпт."),
        )

    # Log generation
    await database.log_generation(
        user_id, mode, quality, ratio, prompt, success=(1 if result else 0)
    )

    # RESTART LOGIC: Instead of clearing everything, we go back to menu
    # But we want to allow user to generate again with same settings OR choose new mode
    await context.bot.send_message(
        chat_id=chat_id,
        text="Готово! Что дальше?",
        reply_markup=mode_keyboard(),
    )
    context.user_data.clear()
    return CHOOSE_MODE


# ── Wrong-State Hints ────────────────────────────────────────────────────────


async def photo_in_prompt_state(update, context):
    mode = context.user_data.get("mode", "")
    if mode == MODE_TXT2IMG:
        await update.message.reply_text(
            ui.error_text(
                "Режим «Текст -> Изображение» — жду текст, а не фото.\n"
                "Для редактирования фото нажми /start и выбери «Фото -> Фото»."
            )
        )
    else:
        await update.message.reply_text(
            ui.error_text("Фото уже загружено. Отправь текст или голосовое.")
        )
    return AWAITING_PROMPT


async def text_in_photo_state(update, context):
    await update.message.reply_text(
        ui.error_text("Жду фотографию. Отправь фото или нажми /start для другого режима.")
    )
    return AWAITING_PHOTO


async def voice_in_photo_state(update, context):
    await update.message.reply_text(
        ui.error_text("Жду фотографию, а не голосовое. Отправь фото.")
    )
    return AWAITING_PHOTO


async def text_in_multi_photos(update, context):
    count = len(context.user_data.get("multi_images", []))
    await update.message.reply_text(
        ui.error_text("Жду фотографии. Отправь фото или нажми Готово."),
        reply_markup=done_photos_keyboard(count),
    )
    return AWAITING_MULTI_PHOTOS


async def voice_in_multi_photos(update, context):
    count = len(context.user_data.get("multi_images", []))
    await update.message.reply_text(
        ui.error_text("Жду фотографии, а не голосовое. Отправь фото."),
        reply_markup=done_photos_keyboard(count),
    )
    return AWAITING_MULTI_PHOTOS


# ── Utility Commands ─────────────────────────────────────────────────────────


async def help_command(update, context):
    text = (
        "🎨 Nano Banana Pro\n"
        "Генерация изображений на базе AI\n"
        "\n"
        "📌 Команды:\n"
        "/start — главное меню\n"
        "/help — справка\n"
        "/cancel — отмена\n"
        "\n"
        "🎯 Режимы:\n"
        "🎨 Текст -> Изображение\n"
        "✏️ Фото -> Фото (редактирование)\n"
        "🧩 Мульти-фото (микс/коллаж)\n"
        "\n"
        "⚙️ Настройки:\n"
        "📐 Соотношение: 1:1, 16:9, 9:16 и др.\n"
        "🎞 Качество: 1K, 2K, 4K\n"
        "🔍 Google Search — реальные данные из интернета\n"
        "✨ Улучшение промпта — AI допишет детали\n"
        "\n"
        "🎤 Можно отправлять голосовые вместо текста"
    )
    await update.message.reply_text(text)


async def cancel(update, context):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Отменено\n\nВыбери режим:",
        reply_markup=mode_keyboard(),
    )
    return CHOOSE_MODE


async def error_handler(update, context):
    logger.error(msg="Exception while handling update:", exc_info=context.error)

async def global_trace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("RECEIVED UPDATE: %s", update.to_dict())
