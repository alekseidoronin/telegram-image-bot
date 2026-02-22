import logging
import asyncio
import uvicorn

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

import database
from admin import app as admin_app
from config import (
    TELEGRAM_BOT_TOKEN,
    GEMINI_API_KEY,
    ADMIN_PORT,
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
    RATIO_PREFIX,
    QUALITY_PREFIX,
    ACTION_ENHANCE,
    ACTION_GENERATE,
    ACTION_DONE_PHOTOS,
    ACTION_MENU,
    ACTION_SEARCH_ON,
    ACTION_SEARCH_OFF,
)
from handlers import (
    start,
    go_menu,
    mode_chosen,
    ratio_chosen,
    quality_chosen,
    search_chosen,
    photo_received,
    multi_photo_received,
    multi_photos_done,
    prompt_received,
    voice_received,
    enhance_prompt_handler,
    generate_handler,
    photo_in_prompt_state,
    text_in_photo_state,
    voice_in_photo_state,
    text_in_multi_photos,
    voice_in_multi_photos,
    global_trace,
    help_command,
    cancel,
    error_handler,
    admin_command,
    language_command,
    set_language_callback,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def post_init(application):
    await application.bot.set_my_commands([
        ("start", "Главное меню / Main menu"),
        ("language", "Сменить язык / Change language"),
        ("help", "Справка / Help"),
        ("cancel", "Отмена / Cancel"),
    ])

async def run_bot():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set")
        return

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .concurrent_updates(True)
        .post_init(post_init)
        .build()
    )

    menu_handler = CallbackQueryHandler(go_menu, pattern="^" + ACTION_MENU + "$")

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_MODE: [
                CallbackQueryHandler(
                    mode_chosen,
                    pattern="^(" + MODE_TXT2IMG + "|" + MODE_IMG2IMG + "|" + MODE_MULTI + ")$",
                ),
                CallbackQueryHandler(language_command, pattern="^btn_language$"),
                menu_handler,
            ],
            CHOOSE_RATIO: [
                CallbackQueryHandler(ratio_chosen, pattern="^" + RATIO_PREFIX),
                menu_handler,
            ],
            CHOOSE_QUALITY: [
                CallbackQueryHandler(quality_chosen, pattern="^" + QUALITY_PREFIX),
                menu_handler,
            ],
            CHOOSE_SEARCH: [
                CallbackQueryHandler(
                    search_chosen,
                    pattern="^(" + ACTION_SEARCH_ON + "|" + ACTION_SEARCH_OFF + ")$",
                ),
                menu_handler,
            ],
            AWAITING_PHOTO: [
                MessageHandler(filters.PHOTO, photo_received),
                MessageHandler(filters.TEXT & ~filters.COMMAND, text_in_photo_state),
                MessageHandler(filters.VOICE, voice_in_photo_state),
            ],
            AWAITING_MULTI_PHOTOS: [
                MessageHandler(filters.PHOTO, multi_photo_received),
                CallbackQueryHandler(multi_photos_done, pattern="^" + ACTION_DONE_PHOTOS + "$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, text_in_multi_photos),
                MessageHandler(filters.VOICE, voice_in_multi_photos),
                menu_handler,
            ],
            AWAITING_PROMPT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_received),
                MessageHandler(filters.VOICE, voice_received),
                MessageHandler(filters.PHOTO, photo_in_prompt_state),
            ],
            CONFIRM_PROMPT: [
                CallbackQueryHandler(enhance_prompt_handler, pattern="^" + ACTION_ENHANCE + "$"),
                CallbackQueryHandler(generate_handler, pattern="^" + ACTION_GENERATE + "$"),
                menu_handler,
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
            CommandHandler("help", help_command),
            CommandHandler("admin", admin_command),
            CommandHandler("language", language_command),
        ],
        allow_reentry=True,
        per_message=False,
    )

    application.add_handler(MessageHandler(filters.ALL, global_trace), group=-1)
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(set_language_callback, pattern="^setlang_"))
    application.add_error_handler(error_handler)

    logger.info("Bot is starting...")
    
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        # Keep running until cancelled
        while True:
            await asyncio.sleep(1)


async def run_admin():
    config = uvicorn.Config(admin_app, host="0.0.0.0", port=ADMIN_PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    # Initialize database
    await database.init_db()
    
    await asyncio.gather(
        run_bot(),
        run_admin()
    )


if __name__ == "__main__":
    asyncio.run(main())
