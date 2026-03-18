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
    ]
    if is_admin:
        # Standard URL button because Mini App requires HTTPS
        keyboard.append([
            InlineKeyboardButton(
                t("btn_admin", lang), 
                url=ADMIN_URL
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
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru"),
         InlineKeyboardButton("🇬🇧 English", callback_data="setlang_en")],
        [InlineKeyboardButton("🇸🇦 العربية", callback_data="setlang_ar"),
         InlineKeyboardButton("🇫🇷 Français", callback_data="setlang_fr")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="setlang_de"),
         InlineKeyboardButton("🇮🇹 Italiano", callback_data="setlang_it")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="setlang_es"),
         InlineKeyboardButton("🇰🇬 Кыргызча", callback_data="setlang_ky")],
        [InlineKeyboardButton("🇺🇿 O'zbek", callback_data="setlang_uz"),
         InlineKeyboardButton("🇧🇾 Беларуская", callback_data="setlang_be")],
        [InlineKeyboardButton("🇹🇯 Тоҷикӣ", callback_data="setlang_tg"),
         InlineKeyboardButton("🇹🇲 Türkmen", callback_data="setlang_tk")],
    ])

def buy_keyboard(lang="ru"):
    # Package format: select_package_{id}_{amount}_{price_rub}
    # Package IDs: 1, 10, 50, 100
    # Package amounts match IDs
    # Prices: 15, 100, 400, 700
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("btn_buy_1", lang), callback_data="select_package_1_1_15")],
        [InlineKeyboardButton(t("btn_buy_10", lang), callback_data="select_package_10_10_100")],
        [InlineKeyboardButton(t("btn_buy_50", lang), callback_data="select_package_50_50_400")],
        [InlineKeyboardButton(t("btn_buy_100", lang), callback_data="select_package_100_100_700")],
        [InlineKeyboardButton(t("btn_menu", lang), callback_data=ACTION_MENU)]
    ])

def profile_keyboard(lang="ru"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="💎 Купить генерации", callback_data="open_packages")],
        [InlineKeyboardButton(text="📜 Правила сервиса", url='https://neuronanobanana.duckdns.org/oferta')],
        [InlineKeyboardButton(t("btn_menu", lang), callback_data=ACTION_MENU)]
    ])

def get_gateway_selection_keyboard(package_id, price_rub, stars_price):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text=f"⭐️ Telegram Stars ({stars_price})", callback_data=f"buy_stars_{package_id}")],
        [InlineKeyboardButton(text=f"💳 Карта РФ (YooMoney) - {price_rub}₽", callback_data=f"buy_yoomoney_{package_id}")],
        [InlineKeyboardButton(text=f"🪙 Криптовалюта (NOWPayments)", callback_data=f"buy_crypto_{package_id}")],
        [InlineKeyboardButton(text="🔙 Назад к пакетам", callback_data="open_packages")],
        [InlineKeyboardButton(text="📜 Правила сервиса", url='https://neuronanobanana.duckdns.org/oferta')]
    ])

def model_keyboard(current_model: str, lang: str = "ru"):
    """Keyboard for selecting image generation model (Nano Banana series)."""
    from config import SET_MODEL_PREFIX, MODEL_BANANA_PRO, MODEL_BANANA_2
    models = [
        (MODEL_BANANA_2,   "🍌 Nanao Banana (Standard — дешевле)"),
        (MODEL_BANANA_PRO, "💎 Nanao Banana Pro (детальнее)"),
    ]
    rows = []
    for model_id, label in models:
        check = "✅ " if current_model == model_id else ""
        rows.append([InlineKeyboardButton(check + label, callback_data=SET_MODEL_PREFIX + model_id)])
    rows.append([InlineKeyboardButton("🔙 Назад" if lang == "ru" else "🔙 Back", callback_data=ACTION_MENU)])
    return InlineKeyboardMarkup(rows)
