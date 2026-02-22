"""
UI formatting: messages, progress bar.
"""

import asyncio
import logging
import time

from config import (
    MODE_ICONS,
    QUALITY_ICONS,
)
from i18n import t

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
    "4K": 120,
}


async def run_progress_bar(message, quality="1K", stop_event=None, lang="ru"):
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

        text = t("status_generating", lang, bar=bar, pct=pct, remaining=remaining)

        try:
            await message.edit_text(text)
        except Exception:
            pass

        wait_time = estimated / total_frames
        if stop_event:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=wait_time)
                if stop_event.is_set():
                    break
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(wait_time)

    if not (stop_event and stop_event.is_set()):
        try:
            await message.edit_text(t("status_done", lang))
        except Exception:
            pass


# ── Message Formatting ───────────────────────────────────────────────────────


def get_lang(context):
    return context.user_data.get("lang", "ru")

def welcome_text(lang="ru"):
    return t("welcome", lang)

def settings_line(context):
    lang = get_lang(context)
    mode = context.user_data.get("mode", "")
    ratio = context.user_data.get("aspect_ratio", "")
    quality = context.user_data.get("quality", "")
    search = context.user_data.get("search", False)
    
    icon = MODE_ICONS.get(mode, "")
    parts = []
    if mode:
        parts.append(icon + " " + t("label_" + mode, lang))
    if ratio:
        parts.append("📐 " + ratio)
    if quality:
        parts.append(QUALITY_ICONS.get(quality, "") + " " + quality)
    if search:
        parts.append("🔍 Google")
    return "  ".join(parts)

def ratio_header(context):
    lang = get_lang(context)
    mode = context.user_data.get("mode", "")
    icon = MODE_ICONS.get(mode, "")
    label = t("label_" + mode, lang)
    
    details = t(f"details_{mode}", lang) if mode else ""
    return icon + " " + label + "\nℹ️ " + details + "\n" + t("choose_ratio", lang)

def quality_header(context):
    lang = get_lang(context)
    line = settings_line(context)
    return line + "\n\n" + t("quality_header", lang)

def search_header(context):
    lang = get_lang(context)
    line = settings_line(context)
    return line + "\n\n" + t("search_header", lang)

def prompt_header(context):
    lang = get_lang(context)
    line = settings_line(context)
    mode = context.user_data.get("mode", "")
    
    if mode == "img2img":
        hint = t("prompt_img2img", lang)
    elif mode == "multi":
        hint = t("prompt_multi", lang)
    else:
        hint = t("prompt_txt2img", lang)
        
    return line + hint

def photo_count_text(count, lang="ru"):
    if count >= 14:
        return t("photo_count_max", lang, count=count)
    elif count < 2:
        return t("photo_count_need", lang, count=count, need=2-count)
    else:
        return t("photo_count_ok", lang, count=count)

def prompt_confirm_text(prompt, context):
    lang = get_lang(context)
    line = settings_line(context)
    return line + "\n\n" + t("prompt_confirm", lang, prompt=prompt)

def enhanced_prompt_text(prompt, lang="ru"):
    return t("enhanced_prompt", lang, prompt=prompt)

def error_text(hint, lang="ru"):
    return t("error_prefix", lang, hint=hint)
