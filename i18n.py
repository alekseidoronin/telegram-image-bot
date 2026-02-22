"""
Internationalization (i18n) strings for Nano Banana Pro.
"""

STRINGS = {
    "ru": {
        "welcome": (
            "🍌 <b>Nano Banana Pro</b> 🎨\n"
            "<i>Генерация изображений на базе передового AI</i>\n\n"
            "💠 <b>Текст -> Изображение</b>\n"
            "Напиши текст, и я нарисую картинку по твоему описанию.\n\n"
            "💠 <b>Фото -> Фото</b>\n"
            "Пришли своё фото и напиши, как его изменить (например, <i>«одень в деловой костюм»</i>).\n\n"
            "💠 <b>Мульти-фото</b>\n"
            "Пришли несколько фото, и я смешаю их/создам крутой коллаж.\n\n"
            "👇 <b>Выбери нужный режим ниже:</b>"
        ),
        "btn_txt2img": "🎨 Текст -> Изображение",
        "btn_img2img": "✏️ Фото -> Фото (редактирование)",
        "btn_multi": "🧩 Мульти-фото (микс/коллаж)",
        "btn_menu": "↩️ Главное меню",
        "btn_language": "🌍 Язык / Language",
        "btn_admin": "👑 Админ-панель",
        "btn_search_on": "🔍 Да, включить",
        "btn_search_off": "❌ Нет",
        "btn_enhance": "✨ Улучшить промпт",
        "btn_generate": "🚀 Генерировать",
        "status_generating": "⏳ Генерация...\n\n[ {bar} ] {pct}%\n⏱ ~{remaining} сек.",
        "status_done": "⏳ Генерация...\n\n[ ▓▓▓▓▓▓▓▓▓▓ ] 100%\n⏱ Почти готово...",
        
        "label_txt2img": "Текст -> Изображение",
        "label_img2img": "Фото -> Фото",
        "label_multi": "Мульти-фото (микс)",
        
        "ratio_1:1": "1:1 (Квадрат ⬛)",
        "ratio_16:9": "16:9 (Горизонт 🖥)",
        "ratio_9:16": "9:16 (Вертикаль 📱)",
        "ratio_4:3": "4:3 (Фото 📷)",
        "ratio_3:4": "3:4 (Портрет 🗿)",
        "ratio_3:2": "3:2 (Широкое 🖼)",
        "ratio_2:3": "2:3 (Вертикаль 📏)",
        "ratio_4:5": "4:5 (Пост 📱)",
        "ratio_5:4": "5:4 (Пост 📏)",
        "ratio_21:9": "21:9 (Кино 🎬)",
        
        "details_txt2img": "Я сгенерирую новую картинку с нуля по твоему текстовому описанию.\n",
        "details_img2img": "Я изменю твоё фото: можно переодеться, поменять фон или стиль.\n",
        "details_multi": "Я возьму несколько фото (до 14) и соединю их в одну композицию.\n",
        "choose_ratio": "📐 Выбери соотношение сторон (формат картинки):",
        
        "quality_header": "🎞 Выбери качество:\n📱 1K — быстро (для соцсетей)\n🖥 2K — баланс (золотая середина)\n🎬 4K — максимум (высокая детализация)",
        "search_header": "🔍 Google Search\n\nИспользовать реальные данные из интернета для генерации?\n(полезно для генерации актуальных событий или точных фактов)",
        
        "prompt_img2img": "\n\n📸 <b>Отправь фото для редактирования</b>\n\n<i>Примеры запросов (отправь вместе с фото):</i>\n• переодень в деловой костюм\n• измени фон на киберпанк город\n• сделай стиль аниме",
        "prompt_multi": "\n\n📸 <b>Отправь от 2 до 14 фото</b>\n\nСначала загрузи все фото по очереди, нажми Готово, а потом напиши промпт.\n<i>Пример: «смешай стиль первого фото с лицом со второго»</i>",
        "prompt_txt2img": "\n\n✍️ <b>Отправь текст или 🎤 голосовое сообщение</b>\n\n<i>Пример: «Футуристичный город на Марсе на закате, гиперреализм, 8k»</i>",
        
        "photo_count_max": "📸 {count}/14 — максимум. Нажми Готово ⬇️",
        "photo_count_need": "📸 {count}/14 фото. Нужно ещё минимум {need}",
        "photo_count_ok": "📸 {count}/14 фото. Можешь добавить ещё или нажми Готово ⬇️",
        "btn_done_photos_need": "📸 Загружено: {count} (мин. 2)",
        "btn_done_photos_ok": "✅ Готово ({count}/{mx} фото)",
        
        "prompt_confirm": "💬 <b>Промпт:</b>\n« <i>{prompt}</i> »\n\nУлучшить промпт или генерировать?",
        "enhanced_prompt": "✨ <b>Улучшенный промпт:</b>\n« <i>{prompt}</i> »\n\nГенерируем?",
        "error_prefix": "⚠️ <b>{hint}</b>",
        
        "admin_panel": "👑 <b>Панель администратора</b>\n\n👥 Всего пользователей: {total_users}\n🖼 Успешных генераций: {total_gens}\n💵 Затраты API: ${total_cost:.3f}\n\n<i>Детальная информация по пользователям доступна в веб-панели.</i>",
        "cancel_msg": "Операция отменена. ❌",
        
        "help_msg": (
            "🎨 Nano Banana Pro\n"
            "Генерация изображений на базе AI\n"
            "\n"
            "📌 Команды:\n"
            "/start — главное меню\n"
            "/help — справка\n"
            "/cancel — отмена\n"
            "/language — изменить язык / change language\n"
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
        ),
        
        "limit_exceeded": "К сожалению, ваш дневной лимит генераций исчерпан. Возвращайтесь завтра!",
        "generation_error": "Не удалось сгенерировать. Попробуй другой промпт.",
        "voice_error": "Не удалось распознать. Попробуй ещё раз или отправь текстом.",
        "expected_text": "Режим «Текст -> Изображение» — жду текст, а не фото.\nДля редактирования фото нажми /start и выбери «Фото -> Фото».",
        "photo_already_loaded": "Фото уже загружено. Отправь текст или голосовое.",
        "expected_photo": "Жду фотографию. Отправь фото или нажми /start для другого режима.",
        "expected_photo_not_voice": "Жду фотографию, а не голосовое. Отправь фото.",
        "expected_images_not_text": "Жду фотографии. Отправь фото или нажми Готово.",
        "expected_images_not_voice": "Жду фотографии, а не голосовое. Отправь фото.",
        
        "msg_done": "✅ Готово!",
        "msg_what_next": "Готово! Что дальше?",
        "blocked": "Вы заблокированы.",
        "enhancing_prompt": "✨ Улучшаю промпт...",
        "start_generating": "⏳ Запускаю генерацию...",
        
        "lang_changed": "Язык интерфейса успешно изменен на 🇷🇺 Русский.",
        "select_lang": "🌍 Выберите язык интерфейса / Select interface language:"
    },
    "en": {
        "welcome": (
            "🍌 <b>Nano Banana Pro</b> 🎨\n"
            "<i>Image generation powered by cutting-edge AI</i>\n\n"
            "💠 <b>Text -> Image</b>\n"
            "Write a prompt and I will draw a picture based on your description.\n\n"
            "💠 <b>Photo -> Photo</b>\n"
            "Send your photo and describe how to change it (e.g. <i>«dress in a business suit»</i>).\n\n"
            "💠 <b>Multi-photo</b>\n"
            "Send multiple photos and I will mix them or create a cool collage.\n\n"
            "👇 <b>Select a mode below:</b>"
        ),
        "btn_txt2img": "🎨 Text -> Image",
        "btn_img2img": "✏️ Photo -> Photo (edit)",
        "btn_multi": "🧩 Multi-photo (mix/collage)",
        "btn_menu": "↩️ Main menu",
        "btn_language": "🌍 Language",
        "btn_admin": "👑 Admin Panel",
        "btn_search_on": "🔍 Yes, enable",
        "btn_search_off": "❌ No",
        "btn_enhance": "✨ Enhance prompt",
        "btn_generate": "🚀 Generate",
        "status_generating": "⏳ Generating...\n\n[ {bar} ] {pct}%\n⏱ ~{remaining} sec.",
        "status_done": "⏳ Generating...\n\n[ ▓▓▓▓▓▓▓▓▓▓ ] 100%\n⏱ Almost done...",
        
        "label_txt2img": "Text -> Image",
        "label_img2img": "Photo -> Photo",
        "label_multi": "Multi-photo (mix)",
        
        "ratio_1:1": "1:1 (Square ⬛)",
        "ratio_16:9": "16:9 (Landscape 🖥)",
        "ratio_9:16": "9:16 (Portrait 📱)",
        "ratio_4:3": "4:3 (Photo 📷)",
        "ratio_3:4": "3:4 (Portrait 🗿)",
        "ratio_3:2": "3:2 (Wide 🖼)",
        "ratio_2:3": "2:3 (Vertical 📏)",
        "ratio_4:5": "4:5 (Post 📱)",
        "ratio_5:4": "5:4 (Post 📏)",
        "ratio_21:9": "21:9 (Cinema 🎬)",
        
        "details_txt2img": "I will generate a new image from scratch using your text description.\n",
        "details_img2img": "I will modify your photo: change clothes, background or style.\n",
        "details_multi": "I will take multiple photos (up to 14) and blend them into one composition.\n",
        "choose_ratio": "📐 Choose an aspect ratio (image format):",
        
        "quality_header": "🎞 Choose quality:\n📱 1K — fast (for social media)\n🖥 2K — balanced (sweet spot)\n🎬 4K — max (high details)",
        "search_header": "🔍 Google Search\n\nUse real-time data from the internet for generation?\n(useful for current events or precise facts)",
        
        "prompt_img2img": "\n\n📸 <b>Send a photo to edit</b>\n\n<i>Examples (send along with the photo):</i>\n• dress in a business suit\n• change background to cyberpunk city\n• make it anime style",
        "prompt_multi": "\n\n📸 <b>Send between 2 and 14 photos</b>\n\nUpload all photos one by one, press Done, and then write your prompt.\n<i>Example: «blend the style of the first photo with the face from the second»</i>",
        "prompt_txt2img": "\n\n✍️ <b>Send text or a 🎤 voice message</b>\n\n<i>Example: «Futuristic city on Mars at sunset, hyperrealism, 8k»</i>",
        
        "photo_count_max": "📸 {count}/14 — maximum. Press Done ⬇️",
        "photo_count_need": "📸 {count}/14 photos. Need at least {need} more",
        "photo_count_ok": "📸 {count}/14 photos. You can add more or press Done ⬇️",
        "btn_done_photos_need": "📸 Uploaded: {count} (min 2)",
        "btn_done_photos_ok": "✅ Done ({count}/{mx} photos)",
        
        "prompt_confirm": "💬 <b>Prompt:</b>\n« <i>{prompt}</i> »\n\nEnhance prompt or generate now?",
        "enhanced_prompt": "✨ <b>Enhanced prompt:</b>\n« <i>{prompt}</i> »\n\nGenerate?",
        "error_prefix": "⚠️ <b>{hint}</b>",
        
        "admin_panel": "👑 <b>Admin Panel</b>\n\n👥 Total users: {total_users}\n🖼 Successful generations: {total_gens}\n💵 API cost: ${total_cost:.3f}\n\n<i>Detailed info is available in the web panel.</i>",
        "cancel_msg": "Operation cancelled. ❌",
        
        "help_msg": (
            "🎨 Nano Banana Pro\n"
            "AI Image Generation\n"
            "\n"
            "📌 Commands:\n"
            "/start — main menu\n"
            "/help — show help\n"
            "/cancel — cancel action\n"
            "/language — change language\n"
            "\n"
            "🎯 Modes:\n"
            "🎨 Text -> Image\n"
            "✏️ Photo -> Photo (editing)\n"
            "🧩 Multi-photo (mix/collage)\n"
            "\n"
            "⚙️ Settings:\n"
            "📐 Ratio: 1:1, 16:9, 9:16 etc.\n"
            "🎞 Quality: 1K, 2K, 4K\n"
            "🔍 Google Search — real-time web data\n"
            "✨ Enhance prompt — AI will add details\n"
            "\n"
            "🎤 You can send voice messages instead of text"
        ),
        
        "limit_exceeded": "Unfortunately, your daily generation limit has been reached. Come back tomorrow!",
        "generation_error": "Failed to generate. Try another prompt.",
        "voice_error": "Could not recognize audio. Try again or send text.",
        "expected_text": "Mode «Text -> Image» — waiting for text, not photo.\nTo edit a photo use /start and choose «Photo -> Photo».",
        "photo_already_loaded": "Photo is already loaded. Send text or voice message.",
        "expected_photo": "Waiting for a photo. Send a photo or use /start to change mode.",
        "expected_photo_not_voice": "Waiting for a photo, not a voice message. Send a photo.",
        "expected_images_not_text": "Waiting for photos. Send a photo or press Done.",
        "expected_images_not_voice": "Waiting for photos, not a voice message. Send a photo.",
        
        "lang_changed": "Interface language successfully changed to 🇬🇧 English.",
        "select_lang": "🌍 Select interface language / Выберите язык интерфейса:"
    }
}

def t(key, lang="ru", **kwargs):
    language_dict = STRINGS.get(lang)
    if not language_dict:
        language_dict = STRINGS["ru"]
    
    msg = language_dict.get(key, key)
    if kwargs:
        msg = msg.format(**kwargs)
    return msg
