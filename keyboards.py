"""
All inline keyboard builders.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import (
    ADMIN_URL,
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
from i18n import t

def mode_keyboard(lang="ru", is_admin=False):
    keyboard = [
        [InlineKeyboardButton(t("btn_txt2img", lang), callback_data=MODE_TXT2IMG)],
        [InlineKeyboardButton(t("btn_img2img", lang), callback_data=MODE_IMG2IMG)],
        [InlineKeyboardButton(t("btn_multi", lang), callback_data=MODE_MULTI)],
        [InlineKeyboardButton(t("btn_language", lang), callback_data="btn_language")],
    ]
    if is_admin:
        # Mini App (WebApp) button
        keyboard.append([
            InlineKeyboardButton(
                t("btn_admin", lang), 
                web_app=WebAppInfo(url=ADMIN_URL)
            )
        ])
    return InlineKeyboardMarkup(keyboard)


def ratio_keyboard(lang="ru"):
    rows = []
    row = []
    for r in RATIO_OPTIONS:
        label = t("ratio_" + r, lang)
        row.append(InlineKeyboardButton(label, callback_data=RATIO_PREFIX + r))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(t("btn_menu", lang), callback_data=ACTION_MENU)])
    return InlineKeyboardMarkup(rows)


def quality_keyboard(lang="ru"):
    buttons = []
    for q in QUALITY_OPTIONS:
        icon = QUALITY_ICONS.get(q, "")
        buttons.append(
            InlineKeyboardButton(icon + " " + q, callback_data=QUALITY_PREFIX + q)
        )
    return InlineKeyboardMarkup([
        buttons,
        [InlineKeyboardButton(t("btn_menu", lang), callback_data=ACTION_MENU)],
    ])


def search_keyboard(lang="ru"):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("btn_search_on", lang), callback_data=ACTION_SEARCH_ON),
            InlineKeyboardButton(t("btn_search_off", lang), callback_data=ACTION_SEARCH_OFF),
        ],
        [InlineKeyboardButton(t("btn_menu", lang), callback_data=ACTION_MENU)],
    ])


def prompt_keyboard(lang="ru"):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("btn_enhance", lang), callback_data=ACTION_ENHANCE),
            InlineKeyboardButton(t("btn_generate", lang), callback_data=ACTION_GENERATE),
        ],
        [InlineKeyboardButton(t("btn_menu", lang), callback_data=ACTION_MENU)],
    ])


def generate_only_keyboard(lang="ru"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_generate", lang), callback_data=ACTION_GENERATE)],
        [InlineKeyboardButton(t("btn_menu", lang), callback_data=ACTION_MENU)],
    ])


def done_photos_keyboard(count, lang="ru"):
    mx = MAX_REFERENCE_IMAGES
    if count < 2:
        label = t("btn_done_photos_need", lang, count=count)
    else:
        label = t("btn_done_photos_ok", lang, count=count, mx=mx)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=ACTION_DONE_PHOTOS)],
        [InlineKeyboardButton(t("btn_menu", lang), callback_data=ACTION_MENU)],
    ])

def language_keyboard(lang="ru"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="setlang_en")],
    ])
