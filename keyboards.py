"""
All inline keyboard builders.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import (
    ACTION_DONE_PHOTOS,
    ACTION_ENHANCE,
    ACTION_GENERATE,
    ACTION_MENU,
    ACTION_SEARCH_ON,
    ACTION_SEARCH_OFF,
    MODE_IMG2IMG,
    MODE_MULTI,
    MODE_TXT2IMG,
    MAX_REFERENCE_IMAGES,
    QUALITY_ICONS,
    QUALITY_OPTIONS,
    QUALITY_PREFIX,
    RATIO_OPTIONS,
    RATIO_PREFIX,
)


def mode_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🎨 Текст -> Изображение", callback_data=MODE_TXT2IMG,
        )],
        [InlineKeyboardButton(
            "✏️ Фото -> Фото (редактирование)", callback_data=MODE_IMG2IMG,
        )],
        [InlineKeyboardButton(
            "🧩 Мульти-фото (микс/коллаж)", callback_data=MODE_MULTI,
        )],
    ])


def ratio_keyboard():
    rows = []
    row = []
    for r in RATIO_OPTIONS:
        row.append(InlineKeyboardButton(r, callback_data=RATIO_PREFIX + r))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("↩️ Главное меню", callback_data=ACTION_MENU)])
    return InlineKeyboardMarkup(rows)


def quality_keyboard():
    buttons = []
    for q in QUALITY_OPTIONS:
        icon = QUALITY_ICONS.get(q, "")
        buttons.append(
            InlineKeyboardButton(icon + " " + q, callback_data=QUALITY_PREFIX + q)
        )
    return InlineKeyboardMarkup([
        buttons,
        [InlineKeyboardButton("↩️ Главное меню", callback_data=ACTION_MENU)],
    ])


def search_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 Да, включить", callback_data=ACTION_SEARCH_ON),
            InlineKeyboardButton("❌ Нет", callback_data=ACTION_SEARCH_OFF),
        ],
        [InlineKeyboardButton("↩️ Главное меню", callback_data=ACTION_MENU)],
    ])


def prompt_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✨ Улучшить промпт", callback_data=ACTION_ENHANCE),
            InlineKeyboardButton("🚀 Генерировать", callback_data=ACTION_GENERATE),
        ],
        [InlineKeyboardButton("↩️ Главное меню", callback_data=ACTION_MENU)],
    ])


def generate_only_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Генерировать", callback_data=ACTION_GENERATE)],
        [InlineKeyboardButton("↩️ Главное меню", callback_data=ACTION_MENU)],
    ])


def done_photos_keyboard(count):
    mx = MAX_REFERENCE_IMAGES
    if count < 2:
        label = "📸 Загружено: " + str(count) + " (мин. 2)"
    else:
        label = "✅ Готово (" + str(count) + "/" + str(mx) + " фото)"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=ACTION_DONE_PHOTOS)],
        [InlineKeyboardButton("↩️ Главное меню", callback_data=ACTION_MENU)],
    ])
