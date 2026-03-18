import logging
import os
import asyncio
import sys
import uvicorn

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    TypeHandler,
    filters,
)

import database
from admin import app as admin_app
from config import (
    TELEGRAM_BOT_TOKEN,
    GEMINI_API_KEY,
    ADMIN_PORT,
    ADMIN_ID,
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
    SET_MODEL_PREFIX,
    CHOOSE_MODEL_TYPE,
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
    select_package_callback,
    buy_gateway_callback,
    buy_command,
    paysupport_command,
    precheckout_callback,
    successful_payment_callback,
    buy_menu_callback,
    profile_callback,
    balance_command,
    edited_prompt_received,
    verify_sub_callback,
    search_command,
    admin_model_picker_callback,
    set_model_callback,
    payment_done_callback,
    admin_confirm_payment_callback,
    admin_reject_payment_callback,
    debug_banana,
)

logging.getLogger("httpx").setLevel(logging.WARNING)

# Ensure log directory exists inside container
os.makedirs("/app/logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/app/logs/app.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


async def post_init(application):
    await application.bot.set_my_commands([
        ("start",      "Главное меню / Main menu"),
        ("balance",    "Мой профиль / My Profile"),
        ("buy",        "Пополнить баланс / Top up balance"),
        ("language",   "Сменить язык / Change language"),
        ("paysupport", "Связь с разработчиком / Contact Developer"),
        ("help",       "Справка / Help"),
        ("search",     "Поиск по смыслу / Semantic Search"),
        ("cancel",     "Отмена / Cancel"),
    ])
    try:
        await application.bot.send_message(chat_id=ADMIN_ID, text="🔄 Бот успешно запущен и готов к работе.")
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")

async def run_bot(application):
    try:
        menu_handler = CallbackQueryHandler(go_menu, pattern="^" + ACTION_MENU + "$")

        conv_handler = ConversationHandler(
                entry_points=[
                    CommandHandler("start", start),
                ],
            states={
                CHOOSE_MODEL_TYPE: [
                    CallbackQueryHandler(set_model_callback, pattern="^" + SET_MODEL_PREFIX),
                    menu_handler,
                ],
                CHOOSE_MODE: [
                    CallbackQueryHandler(
                        mode_chosen,
                        pattern="^(" + MODE_TXT2IMG + "|" + MODE_IMG2IMG + "|" + MODE_MULTI + ")$",
                    ),
                    CallbackQueryHandler(language_command, pattern="^btn_language$"),
                    CallbackQueryHandler(buy_menu_callback, pattern="^(btn_buy|open_packages)$"),
                    CallbackQueryHandler(profile_callback, pattern="^btn_profile$"),
                    CallbackQueryHandler(select_package_callback, pattern="^select_package_"),
                    CallbackQueryHandler(buy_gateway_callback, pattern="^buy_"),
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
                    MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT, edited_prompt_received),
                    MessageHandler(filters.VOICE, voice_received),
                    MessageHandler(filters.PHOTO, photo_in_prompt_state),
                ],
                CONFIRM_PROMPT: [
                    CallbackQueryHandler(enhance_prompt_handler, pattern="^" + ACTION_ENHANCE + "$"),
                    CallbackQueryHandler(generate_handler, pattern="^" + ACTION_GENERATE + "$"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_received),
                    MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT, edited_prompt_received),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CommandHandler("start", start),
                CommandHandler("help", help_command),
                CommandHandler("admin", admin_command),
                CommandHandler("language", language_command),
                CommandHandler("buy", buy_command),
                CommandHandler("balance", balance_command),
                CommandHandler("search", search_command),
                CommandHandler("paysupport", paysupport_command),
                CallbackQueryHandler(admin_model_picker_callback, pattern="^admin_model_picker$"),
                CallbackQueryHandler(set_model_callback, pattern="^" + SET_MODEL_PREFIX),
                MessageHandler(filters.UpdateType.EDITED_MESSAGE, lambda u, c: None),
            ],
            allow_reentry=True,
            per_message=False,
        )

        # Global handlers (work regardless of conversation state)
        application.add_handler(CallbackQueryHandler(buy_menu_callback, pattern="^(btn_buy|open_packages)$"))
        application.add_handler(CommandHandler("paysupport", paysupport_command))
        application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
        application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
        application.add_handler(MessageHandler(filters.ALL, global_trace), group=-5)

        # Force Sub callback
        application.add_handler(CallbackQueryHandler(verify_sub_callback, pattern='^check_force_sub$'))

        # Payment confirmation handlers (must be before conv_handler)
        application.add_handler(CallbackQueryHandler(payment_done_callback, pattern=r"^paid_done:"))
        application.add_handler(CallbackQueryHandler(admin_confirm_payment_callback, pattern=r"^adm_confirm:"))
        application.add_handler(CallbackQueryHandler(admin_reject_payment_callback, pattern=r"^adm_reject:"))

        # Hidden admin-only debug command (not in public menu)
        application.add_handler(CommandHandler("debug_banana", debug_banana))

        application.add_handler(conv_handler)
        application.add_handler(CallbackQueryHandler(set_language_callback, pattern="^setlang_"))
        application.add_handler(CallbackQueryHandler(admin_model_picker_callback, pattern="^admin_model_picker$"))
        application.add_handler(CallbackQueryHandler(set_model_callback, pattern="^" + SET_MODEL_PREFIX))
        application.add_error_handler(error_handler)

        logger.info("Bot is starting...")
        
        async with application:
            await application.initialize()
            await application.start()
            await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            # Keep running until cancelled
            while True:
                await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"Bot failed to start: {e}")
        sys.exit(1)

async def run_admin(application):
    # Set the bot application on the admin app instance
    admin_app.state.bot_app = application
    config = uvicorn.Config(admin_app, host="0.0.0.0", port=ADMIN_PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    logger.info("MARKER: Bot main() starting...")
    # Initialize database
    await database.init_db()
    
    # Fetch settings from DB
    db_token = await database.get_setting("TELEGRAM_BOT_TOKEN")
    token = db_token if db_token else TELEGRAM_BOT_TOKEN
    
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set in DB or config.py")
        return

    application = (
        Application.builder()
        .token(token)
        .concurrent_updates(True)
        .post_init(post_init)
        .build()
    )
    
    try:
        await asyncio.gather(
            run_bot(application),
            run_admin(application)
        )
    except asyncio.CancelledError:
        logger.info("Termination signal received.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
