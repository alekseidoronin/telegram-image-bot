"""
Voice message transcription via AssemblyAI.
"""

import logging
import os
import tempfile

import assemblyai as aai

logger = logging.getLogger(__name__)


async def transcribe(api_key, voice_bytes):
    """Transcribe voice bytes to text.

    Returns transcribed text or None on failure.
    """
    if not api_key:
        return None

    try:
        aai.settings.api_key = api_key

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(voice_bytes)
            tmp_path = f.name

        transcriber = aai.Transcriber()
        config = aai.TranscriptionConfig(language_detection=True)
        transcript = transcriber.transcribe(tmp_path, config=config)

        os.unlink(tmp_path)

        if transcript.status == aai.TranscriptStatus.error:
            logger.error("Transcription error: %s", transcript.error)
            return None

        return transcript.text
    except Exception:
        logger.exception("transcribe failed")
        return None
