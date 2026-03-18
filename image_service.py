"""
Gemini API: image generation via REST API.

Based on official docs: https://ai.google.dev/gemini-api/docs/image-generation
Model: gemini-3-pro-image-preview (NeuroNanoBanana)
Supports: imageSize (1K/2K/4K), aspectRatio, multi-image input (up to 14 refs)
"""

import asyncio
import base64
import functools
import imghdr
import logging
import time
from io import BytesIO
from typing import List, Optional

import requests as http_requests
from google import genai
from PIL import Image

from config import (
    API_URL,
    TEXT_MODEL,
    MAX_RETRIES,
    STANDARD_MODEL_ID,
    PRO_MODEL_ID,
    STANDARD_COSTS,
    PRO_COSTS,
)

logger = logging.getLogger(__name__)


def get_deduction_amount(model_id: str, quality: str) -> int:
    """
    Unified credit logic.

    - Standard models (Flash) use base weight 1.
    - Pro models use base weight 3.
    - 4K всегда удваивает базовый вес.
    - 1K и 2K стоят одинаково по кредитам.
    """
    model = (model_id or "").lower()
    is_pro = "pro" in model
    base_weight = 3 if is_pro else 1
    if quality == "4K":
        return base_weight * 2
    return base_weight


def get_real_api_cost(model_id: str, quality: str) -> float:
    """
    Return real API cost in USD for given model / quality.
    Falls back to 1K tier if quality is unknown.
    """
    model = (model_id or "").lower()
    is_pro = "pro" in model
    table = PRO_COSTS if is_pro else STANDARD_COSTS
    q = quality if quality in table else "1K"
    return float(table.get(q, table["1K"]))


def _detect_mime(image_bytes):
    """Detect actual image MIME type."""
    img_type = imghdr.what(None, h=image_bytes)
    if img_type == "jpeg":
        return "image/jpeg"
    elif img_type == "png":
        return "image/png"
    elif img_type == "gif":
        return "image/gif"
    elif img_type == "webp":
        return "image/webp"
    return "image/jpeg"  # default


def _image_to_base64(image_bytes):
    return base64.b64encode(image_bytes).decode("utf-8")


def _image_part(image_bytes):
    """Create an inlineData part from image bytes (per docs format)."""
    return {
        "inlineData": {
            "mimeType": _detect_mime(image_bytes),
            "data": _image_to_base64(image_bytes),
        }
    }


def _call_api_sync(api_key, parts, aspect_ratio="1:1", quality="1K", search=False, image_model=None):
    """Synchronous Gemini REST API call with retry logic."""
    from config import IMAGE_MODEL as DEFAULT_IMAGE_MODEL
    model_name = image_model or DEFAULT_IMAGE_MODEL
    endpoint_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    
    # Build imageConfig
    image_config = {}
    if aspect_ratio:
        image_config["aspectRatio"] = aspect_ratio
    if quality and quality != "1K":
        image_config["imageSize"] = quality

    payload = {
        "contents": [{
            "role": "user",
            "parts": parts,
        }],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
        },
    }

    if image_config:
        payload["generationConfig"]["imageConfig"] = image_config

    # Google Search grounding — per docs: tools: [{"google_search": {}}]
    if search:
        payload["tools"] = [{"google_search": {}}]

    timeout = 180 if quality == "4K" else 120

    # Retry logic for transient 400/500 errors
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = http_requests.post(
                endpoint_url + "?key=" + api_key,
                json=payload,
                timeout=timeout,
            )
            data = resp.json()
        except Exception:
            logger.exception("API request failed (attempt %d)", attempt + 1)
            if attempt < MAX_RETRIES:
                time.sleep(2 * (attempt + 1))
                continue
            return []

        if "error" in data:
            error_msg = data["error"].get("message", "unknown")
            error_code = data["error"].get("code", 0)
            logger.error("API error (attempt %d): %s", attempt + 1, error_msg)
            # Retry on 400 internal errors and 500s
            if error_code in (400, 500, 503) and attempt < MAX_RETRIES:
                time.sleep(2 * (attempt + 1))
                continue
            return []

        # Success — basic usage logging for cost control
        try:
            model_version = data.get("modelVersion") or data.get("model") or model_name
            usage = data.get("usageMetadata") or data.get("usage") or {}
            logger.info("Image generation usage — model=%s usage=%s", model_version, usage)
        except Exception:
            logger.exception("Failed to log image usage metadata")

        # Success — extract images
        images = []
        candidates = data.get("candidates", [])
        if not candidates:
            logger.warning("No candidates in response (attempt %d)", attempt + 1)
            if attempt < MAX_RETRIES:
                time.sleep(2 * (attempt + 1))
                continue
            return []

        response_parts = candidates[0].get("content", {}).get("parts", [])
        for part in response_parts:
            if "inlineData" in part:
                try:
                    img_data = base64.b64decode(part["inlineData"]["data"])
                    buf = BytesIO(img_data)
                    img = Image.open(buf)
                    out = BytesIO()
                    img.save(out, format="PNG")
                    images.append(out.getvalue())
                except Exception:
                    logger.exception("Failed to decode image from response")
            elif "text" in part:
                logger.info("Model response text: %s", part["text"][:100])

        if images:
            return images

        # No images extracted — retry
        if attempt < MAX_RETRIES:
            logger.warning("No images in response, retrying...")
            time.sleep(2 * (attempt + 1))
            continue

    return []



async def _call_api(api_key, parts, aspect_ratio="1:1", quality="1K", search=False, **kwargs):

    """Async wrapper — runs the blocking HTTP call in a thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(
            _call_api_sync,
            api_key, parts,
            aspect_ratio=aspect_ratio,
            quality=quality,
            search=search,
            image_model=kwargs.get("image_model")
        ),
    )


# ── Public API ───────────────────────────────────────────────────────────────


async def enhance_prompt(api_key=None, prompt="", text_model=None):
    """Enhance prompt using Gemini text model via REST API."""
    import database
    from config import TEXT_MODEL as DEFAULT_TEXT_MODEL, GEMINI_API_KEY as DEFAULT_API_KEY
    
    # Dynamic settings resolution
    actual_api_key = api_key or await database.get_setting("GEMINI_API_KEY")
    actual_model = text_model or await database.get_setting("TEXT_MODEL")
    
    def _do_enhance():
        endpoint_url = f"https://generativelanguage.googleapis.com/v1beta/models/{actual_model}:generateContent"
        payload = {
            "contents": [{
                "parts": [{
                    "text":
                        "You are an assistant that gently refines prompts for AI image generation.\n"
                        "Your main goal is to KEEP the user's original idea, style and constraints exactly the same.\n"
                        "Do NOT change the genre, main subject, composition, or art style unless the user explicitly asks for it.\n"
                        "You may: slightly clarify details (lighting, atmosphere, camera angle) and fix grammar.\n"
                        "You must NOT remove important objects, people, brands, text, or restrictions from the original prompt.\n"
                        "Keep the result short (1–2 sentences).\n"
                        "Return ONLY the improved prompt text, without quotes or explanations.\n\n"
                        "Original prompt:\n"
                        + prompt
                }]
            }]
        }
        for attempt in range(3):
            try:
                resp = http_requests.post(endpoint_url + "?key=" + actual_api_key, json=payload, timeout=60)
                if resp.status_code == 200:
                    data = resp.json()
                    if "candidates" in data and data["candidates"]:
                        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception:
                pass
            time.sleep(2)
        return None

    loop = asyncio.get_event_loop()
    try:
        enhanced = await loop.run_in_executor(None, _do_enhance)
        return enhanced if enhanced else prompt
    except Exception:
        logger.exception("enhance_prompt failed")
        return prompt


async def text_to_image(api_key, prompt, aspect_ratio="1:1", quality="1K", search=False, image_model=None):
    """Generate image from text prompt."""
    try:
        parts = [{"text": prompt}]
        images = await _call_api(api_key, parts, aspect_ratio, quality, search=search, image_model=image_model)
        return images[0] if images else None
    except Exception:
        logger.exception("text_to_image failed")
        return None


async def image_to_image(api_key=None, image_bytes=None, prompt="", aspect_ratio="1:1", quality="1K", search=False, image_model=None):
    """Edit an existing image based on prompt."""
    import database
    from config import GEMINI_API_KEY as DEFAULT_API_KEY, IMAGE_MODEL as DEFAULT_IMAGE_MODEL

    actual_api = api_key or await database.get_setting("GEMINI_API_KEY")
    actual_model = image_model or await database.get_setting("IMAGE_MODEL")

    try:
        parts = [
            _image_part(image_bytes),
            {"text": (
                "This is my original photo. Make a precise edit: " + prompt + ". "
                "CRITICAL INSTRUCTION: You MUST return exactly ONE single cohesive picture. "
                "DO NOT generate a collage, DO NOT generate a grid, DO NOT generate multiple variations, DO NOT generate a split-screen. "
                "The output MUST be a standard single-frame portrait/photo of ONE subject. "
                "Keep everything else exactly the same — same background, people, colors, composition, lighting, angle. "
                "Only change what was requested. Do not regenerate the photo from scratch."
            )},
        ]
        images = await _call_api(actual_api, parts, aspect_ratio, quality, search=search, image_model=actual_model)
        return images[0] if images else None
    except Exception:
        logger.exception("image_to_image failed")
        return None


async def multi_image(api_key=None, images_bytes=None, prompt="", aspect_ratio="1:1", quality="1K", search=False, image_model=None):
    """Combine multiple images (2-14) based on prompt."""
    import database
    from config import GEMINI_API_KEY as DEFAULT_API_KEY, IMAGE_MODEL as DEFAULT_IMAGE_MODEL

    actual_api = api_key or await database.get_setting("GEMINI_API_KEY")
    actual_model = image_model or await database.get_setting("IMAGE_MODEL")

    try:
        parts = [
            {"text": (
                "I'm giving you " + str(len(images_bytes)) + " reference images. "
                + prompt
            )},
        ]
        for img_bytes in images_bytes:
            parts.append(_image_part(img_bytes))

        images = await _call_api(actual_api, parts, aspect_ratio, quality, search=search, image_model=actual_model)
        return images[0] if images else None
    except Exception:
        logger.exception("multi_image failed")
        return None
