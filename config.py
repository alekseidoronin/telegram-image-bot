"""
Configuration: env vars, constants, state definitions.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ─────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = ""
GEMINI_API_KEY = ""
ASSEMBLYAI_KEY = ""
YOOMONEY_WALLET = os.getenv("YOOMONEY_WALLET", "")
YOOMONEY_SECRET = os.getenv("YOOMONEY_SECRET", "")
NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY", "")
NOWPAYMENTS_IPN_SECRET = os.getenv("NOWPAYMENTS_IPN_SECRET", "")

# Note: These are fallback values. The bot will prefer values from the database
# if they are set in the Admin Dashboard.

# ── Admin & Database ─────────────────────────────────────────────────────────

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_PORT = int(os.getenv("ADMIN_PORT", "8080"))
ADMIN_URL = os.getenv("ADMIN_URL", "https://NeuroNanoBanana.duckdns.org")
ADMIN_ID = 632600126
DEFAULT_TOTAL_LIMIT = 7

# ── Force Sub Settings ───────────────────────────────────────────────────────
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@Doronin_Al")
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/Doronin_Al")
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "Doronin_Al")

# ── Models ───────────────────────────────────────────────────────────────────

# Default models (can be overridden in DB settings)
IMAGE_MODEL = ""
TEXT_MODEL = ""

# Canonical model IDs for image generation
STANDARD_MODEL_ID = "gemini-3.1-flash-image-preview"     # Nano Banana 2 Flash
PRO_MODEL_ID      = "gemini-3-pro-image-preview"         # Nano Banana Pro 2

# Real API costs (USD) per generation, used for margin / analytics
STANDARD_COSTS = {
    "1K": 0.045,
    "2K": 0.067,
    "4K": 0.101,
}

PRO_COSTS = {
    "1K": 0.15,
    "2K": 0.15,
    "4K": 0.30,
}

API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    + IMAGE_MODEL
    + ":generateContent"
)

# ── Conversation States ──────────────────────────────────────────────────────

(
    CHOOSE_MODE,
    CHOOSE_RATIO,
    CHOOSE_QUALITY,
    CHOOSE_SEARCH,
    AWAITING_PHOTO,
    AWAITING_MULTI_PHOTOS,
    AWAITING_PROMPT,
    CONFIRM_PROMPT,
) = range(8)

# ── Callback Data ────────────────────────────────────────────────────────────

MODE_TXT2IMG = "txt2img"
MODE_IMG2IMG = "img2img"
MODE_MULTI = "multi"
RATIO_PREFIX = "ratio_"
QUALITY_PREFIX = "quality_"
ACTION_ENHANCE = "enhance"
ACTION_GENERATE = "generate"
ACTION_DONE_PHOTOS = "done_photos"
ACTION_MENU = "go_menu"
ACTION_SEARCH_ON = "search_on"
ACTION_SEARCH_OFF = "search_off"

# ── Labels ───────────────────────────────────────────────────────────────────

MODE_LABELS = {
    MODE_TXT2IMG: "Текст -> Изображение",
    MODE_IMG2IMG: "Фото -> Фото",
    MODE_MULTI: "Мульти-фото (микс)",
}

MODE_ICONS = {
    MODE_TXT2IMG: "🎨",
    MODE_IMG2IMG: "✏️",
    MODE_MULTI: "🧩",
}

RATIO_LABELS = {
    "1:1": "1:1 (Квадрат ⬛)",
    "16:9": "16:9 (Горизонт 🖥)",
    "9:16": "9:16 (Вертикаль 📱)",
    "4:3": "4:3 (Фото 📷)",
    "3:4": "3:4 (Портрет 🗿)",
    "3:2": "3:2 (Широкое 🖼)",
    "2:3": "2:3 (Вертикаль 📏)",
    "4:5": "4:5 (Пост 📱)",
    "5:4": "5:4 (Пост 📏)",
    "21:9": "21:9 (Кино 🎬)",
}
RATIO_OPTIONS = list(RATIO_LABELS.keys())

QUALITY_OPTIONS = ["1K", "2K", "4K"]

QUALITY_ICONS = {
    "1K": "📱",
    "2K": "🖥",
    "4K": "🎬",
}

# ── Limits ───────────────────────────────────────────────────────────────────

MAX_REFERENCE_IMAGES = 14
MAX_RETRIES = 2

# ── Model Selection ──────────────────────────────────────────────────────────

SET_MODEL_PREFIX = "set_model_"
MODEL_BANANA_PRO = "gemini-3-pro-image-preview"
MODEL_BANANA_2   = "gemini-3.1-flash-image-preview"
MODEL_BANANA     = "gemini-2.5-flash-image"

MODEL_LABELS_GEN = {
    MODEL_BANANA_2:   "🍌 Nanao Banana (Standard)",
    MODEL_BANANA_PRO: "💎 Nanao Banana Pro",
    MODEL_BANANA:     "🌿 Nanao Banana (Legacy)",
}

CHOOSE_MODEL_TYPE = 10  # extra conversation state for model picker
