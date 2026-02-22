"""
Configuration: env vars, constants, state definitions.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ─────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ASSEMBLYAI_KEY = os.getenv("ASSEMBLYAI_KEY", "")

# ── Admin & Database ─────────────────────────────────────────────────────────

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_PORT = int(os.getenv("ADMIN_PORT", "8080"))
DEFAULT_DAILY_LIMIT = 7

# ── Models ───────────────────────────────────────────────────────────────────

IMAGE_MODEL = "gemini-3-pro-image-preview"
TEXT_MODEL = "gemini-2.0-flash"
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
