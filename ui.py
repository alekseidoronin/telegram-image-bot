"""
UI formatting: messages, progress bar.
"""

import asyncio
import logging
import time

from config import (
    MODE_ICONS,
    MODE_LABELS,
    QUALITY_ICONS,
)

logger = logging.getLogger(__name__)

# ── Progress Bar ─────────────────────────────────────────────────────────────

PROGRESS_FRAMES = [
    "▓░░░░░░░░░",
    "▓▓░░░░░░░░",
    "▓▓▓░░░░░░░",
    "▓▓▓▓░░░░░░",
    "▓▓▓▓▓░░░░░",
    "▓▓▓▓▓▓░░░░",
    "▓▓▓▓▓▓▓░░░",
    "▓▓▓▓▓▓▓▓░░",
    "▓▓▓▓▓▓▓▓▓░",
    "▓▓▓▓▓▓▓▓▓▓",
]

ESTIMATED_TIMES = {
    "1K": 35,
    "2K": 50,
    "4K": 70,
}


async def run_progress_bar(message, quality="1K", stop_event=None):
    """Animate a progress bar by editing the message."""
    estimated = ESTIMATED_TIMES.get(quality, 20)
    total_frames = len(PROGRESS_FRAMES)
    start_time = time.time()

    for i in range(total_frames):
        if stop_event and stop_event.is_set():
            break

        elapsed = int(time.time() - start_time)
        remaining = max(0, estimated - elapsed)
        bar = PROGRESS_FRAMES[i]
        pct = int((i + 1) / total_frames * 100)

        text = (
            "⏳ Генерация...\n\n"
            "[ " + bar + " ] " + str(pct) + "%\n"
            "⏱ ~" + str(remaining) + " сек."
        )

        try:
            await message.edit_text(text)
        except Exception:
            pass

        wait_time = estimated / total_frames
        if stop_event:
            try:
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, stop_event.wait, wait_time),
                    timeout=wait_time + 0.5,
                )
                if stop_event.is_set():
                    break
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(wait_time)

    if not (stop_event and stop_event.is_set()):
        try:
            await message.edit_text(
                "⏳ Генерация...\n\n"
                "[ ▓▓▓▓▓▓▓▓▓▓ ] 100%\n"
                "⏱ Почти готово..."
            )
        except Exception:
            pass


# ── Message Formatting ───────────────────────────────────────────────────────


def welcome_text():
    return (
        "🎨 Nano Banana Pro\n"
        "Генерация изображений на базе AI\n\n"
        "Выбери режим:"
    )


def settings_line(context):
    mode = context.user_data.get("mode", "")
    ratio = context.user_data.get("aspect_ratio", "")
    quality = context.user_data.get("quality", "")
    search = context.user_data.get("search", False)
    icon = MODE_ICONS.get(mode, "")
    parts = []
    if mode:
        parts.append(icon + " " + MODE_LABELS.get(mode, mode))
    if ratio:
        parts.append("📐 " + ratio)
    if quality:
        parts.append(QUALITY_ICONS.get(quality, "") + " " + quality)
    if search:
        parts.append("🔍 Google")
    return "  ".join(parts)


def ratio_header(context):
    mode = context.user_data.get("mode", "")
    icon = MODE_ICONS.get(mode, "")
    label = MODE_LABELS.get(mode, "")
    return icon + " " + label + "\n\n📐 Выбери соотношение сторон:"


def quality_header(context):
    line = settings_line(context)
    return (
        line + "\n\n"
        "🎞 Выбери качество:\n\n"
        "📱 1K — быстро\n"
        "🖥 2K — баланс\n"
        "🎬 4K — максимум"
    )


def search_header(context):
    line = settings_line(context)
    return (
        line + "\n\n"
        "🔍 Google Search\n\n"
        "Использовать реальные данные из интернета для генерации?\n"
        "(погода, события, актуальная информация)"
    )


def prompt_header(context):
    line = settings_line(context)
    mode = context.user_data.get("mode", "")
    if mode == "img2img":
        hint = "\n\n📸 Отправь фото для редактирования"
    elif mode == "multi":
        hint = "\n\n📸 Отправь от 2 до 14 фото — по одной или несколько сразу"
    else:
        hint = "\n\n✍️ Отправь текст или 🎤 голосовое сообщение"
    return line + hint


def photo_count_text(count):
    if count >= 14:
        return "📸 " + str(count) + "/14 — максимум. Нажми Готово ⬇️"
    elif count < 2:
        need = 2 - count
        return "📸 " + str(count) + "/14 фото. Нужно ещё минимум " + str(need)
    else:
        return "📸 " + str(count) + "/14 фото. Можешь добавить ещё или нажми Готово ⬇️"


def prompt_confirm_text(prompt, context):
    line = settings_line(context)
    return (
        line + "\n\n"
        "💬 Промпт:\n"
        "« " + prompt + " »\n\n"
        "Улучшить промпт или генерировать?"
    )


def enhanced_prompt_text(prompt):
    return (
        "✨ Улучшенный промпт:\n"
        "« " + prompt + " »\n\n"
        "Генерируем?"
    )


def error_text(hint):
    return "⚠️ " + hint
