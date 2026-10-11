import base64
import binascii
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

BACKEND_DIRECTORY = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIRECTORY / ".env")

MURF_GENERATE_URL = "https://api.murf.ai/v1/speech/generate"

DEFAULT_VOICE_ID = "en-US-natalie"
MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_CACHE_ENTRIES = 100
logger = logging.getLogger(__name__)

_speech_cache: dict[tuple[str, str], "GeneratedSpeech"] = {}
_cache_lock = threading.Lock()


def clear_speech_cache() -> None:
    with _cache_lock:
        _speech_cache.clear()


class MurfServiceError(Exception):
    """A safe, user-facing Murf speech-generation failure."""


@dataclass(frozen=True)
class GeneratedSpeech:
    audio_base64: str
    audio_content_type: str


def murf_voice_id() -> str:
    return os.environ.get("MURF_VOICE_ID", DEFAULT_VOICE_ID).strip() or DEFAULT_VOICE_ID


def murf_is_configured() -> bool:
    return bool(os.environ.get("MURF_API_KEY", "").strip())


def generate_speech(
    text: str,
    *,
    api_key: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> GeneratedSpeech:
    configured_key = os.environ.get("MURF_API_KEY", "").strip() if api_key is None else api_key.strip()
    if not configured_key:
        raise MurfServiceError(
            "Murf API key is not configured. Add MURF_API_KEY to backend/.env."
        )

    voice_id = murf_voice_id()
    cache_key = (voice_id, text.strip())
    if transport is None:
        with _cache_lock:
            cached = _speech_cache.get(cache_key)
            if cached is not None:
                return cached
    payload = {
        "text": text,
        "voiceId": voice_id,
        "modelVersion": "GEN2",
        "format": "MP3",
        "channelType": "MONO",
        "sampleRate": 44100,
        "encodeAsBase64": True,
    }
    try:
        with httpx.Client(
            timeout=httpx.Timeout(30.0, connect=5.0),
            transport=transport,
            follow_redirects=False,
        ) as client:
            response = client.post(
                MURF_GENERATE_URL,
                headers={
                    "api-key": configured_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException as error:
        logger.warning("Murf speech request timed out")
        raise MurfServiceError(
            "Murf voice generation timed out. Please try again."
        ) from error
    except httpx.RequestError as error:
        logger.warning("Murf speech request failed: %s", type(error).__name__)
        raise MurfServiceError(
            "Murf could not be reached. Check the backend's internet connection."
        ) from error

    if response.status_code in (401, 403):
        raise MurfServiceError(
            "Murf rejected the API key. Check MURF_API_KEY in backend/.env."
        )
    if response.status_code == 429:
        raise MurfServiceError(
            "Murf rate limit or account quota was reached. Check your Murf API plan."
        )
    if response.status_code in (402, 413):
        raise MurfServiceError(
            "Murf could not process the request under the current account limits."
        )
    if response.status_code >= 500:
        raise MurfServiceError("Murf is temporarily unavailable. Please try again later.")
    if not response.is_success:
        logger.warning("Murf speech request returned HTTP %s", response.status_code)
        raise MurfServiceError(
            "Murf rejected the speech request. Check the configured voice and API settings."
        )

    try:
        response_body = response.json()
    except ValueError as error:
        raise MurfServiceError("Murf returned an unreadable response.") from error

    if not isinstance(response_body, dict):
        raise MurfServiceError("Murf returned an unexpected response format.")

    encoded_audio = response_body.get("encodedAudio")
    if not isinstance(encoded_audio, str) or not encoded_audio:
        raise MurfServiceError(
            "Murf returned no Base64 audio. Check the response format and API settings."
        )

    try:
        audio_bytes = base64.b64decode(encoded_audio, validate=True)
    except (binascii.Error, ValueError) as error:
        raise MurfServiceError("Murf returned invalid Base64 audio.") from error
    if not audio_bytes:
        raise MurfServiceError("Murf returned empty audio.")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise MurfServiceError("The generated audio exceeded the 8 MB response limit.")

    speech = GeneratedSpeech(
        audio_base64=encoded_audio,
        audio_content_type="audio/mpeg",
    )
    if transport is None:
        with _cache_lock:
            if len(_speech_cache) >= MAX_CACHE_ENTRIES:
                _speech_cache.pop(next(iter(_speech_cache)), None)
            _speech_cache[cache_key] = speech
    return speech
