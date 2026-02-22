"""
Gemini API: image generation via REST API.

Based on official docs: https://ai.google.dev/gemini-api/docs/image-generation
Model: gemini-3-pro-image-preview (Nano Banana Pro)
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

from config import API_URL, TEXT_MODEL, MAX_RETRIES

logger = logging.getLogger(__name__)


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


def _call_api_sync(api_key, parts, aspect_ratio="1:1", quality="1K", search=False):
    """Synchronous Gemini REST API call with retry logic.

    Runs in a thread pool via _call_api() to avoid blocking the event loop.
    """
    # Build imageConfig
    image_config = {}
    if aspect_ratio:
        image_config["aspectRatio"] = aspect_ratio
    if quality and quality != "1K":
        image_config["imageSize"] = quality
    
    image_config["numberOfImages"] = 1

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
                API_URL + "?key=" + api_key,
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


async def _call_api(api_key, parts, aspect_ratio="1:1", quality="1K", search=False):
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
        ),
    )


# ── Public API ───────────────────────────────────────────────────────────────


async def enhance_prompt(api_key, prompt):
    """Enhance prompt using Gemini text model."""
    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=TEXT_MODEL,
            contents=[
                "You are an expert prompt engineer for AI image generation. "
                "Enhance the following prompt to produce better, more vivid images. "
                "Use narrative style: describe the scene, lighting, atmosphere, "
                "camera angle, artistic style. "
                "Keep it concise (max 3 sentences). "
                "Return ONLY the enhanced prompt. No quotes, no explanation.\n\n"
                "Original: " + prompt
            ],
        )
        enhanced = response.text.strip()
        return enhanced if enhanced else prompt
    except Exception:
        logger.exception("enhance_prompt failed")
        return prompt


async def text_to_image(api_key, prompt, aspect_ratio="1:1", quality="1K", search=False):
    """Generate image from text prompt.

    Docs: contents = [{"text": "prompt"}]
    """
    try:
        parts = [{"text": prompt}]
        images = await _call_api(api_key, parts, aspect_ratio, quality, search=search)
        return images[0] if images else None
    except Exception:
        logger.exception("text_to_image failed")
        return None


async def image_to_image(api_key, image_bytes, prompt, aspect_ratio="1:1", quality="1K", search=False):
    """Edit an existing image based on prompt.

    Docs: contents = ["Edit this image...", image]
    Per docs, for editing: pass image + editing instructions.
    """
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
        images = await _call_api(api_key, parts, aspect_ratio, quality, search=search)
        return images[0] if images else None
    except Exception:
        logger.exception("image_to_image failed")
        return None


async def multi_image(api_key, images_bytes, prompt, aspect_ratio="1:1", quality="1K", search=False):
    """Combine multiple images (2-14) based on prompt.

    Docs: Gemini 3 Pro supports up to 14 reference images.
    """
    try:
        parts = [
            {"text": (
                "I'm giving you " + str(len(images_bytes)) + " reference images. "
                + prompt
            )},
        ]
        for img_bytes in images_bytes:
            parts.append(_image_part(img_bytes))

        images = await _call_api(api_key, parts, aspect_ratio, quality, search=search)
        return images[0] if images else None
    except Exception:
        logger.exception("multi_image failed")
        return None
