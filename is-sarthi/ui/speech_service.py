"""
IS Sarthi -- Multilingual Voice Integration Service (Sarvam AI).
Provides Speech-to-Text (STT), Text-to-Speech (TTS), and Translation
supporting Hindi, Marathi, English, Telugu, and Tamil.
"""
from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]

DEFAULT_API_KEY = "sk_3mo5y5nl_sB2BreSIHbw6XRFBmw2AUeMz"

SUPPORTED_LANGUAGES: Dict[str, Dict[str, str]] = {
    "en-IN": {
        "label": "English",
        "native": "English",
        "default_speaker": "shubh",
        "flag": "🇬🇧",
    },
    "hi-IN": {
        "label": "Hindi (हिन्दी)",
        "native": "हिन्दी",
        "default_speaker": "ritu",
        "flag": "🇮🇳",
    },
    "mr-IN": {
        "label": "Marathi (मराठी)",
        "native": "मराठी",
        "default_speaker": "shubh",
        "flag": "🇮🇳",
    },
    "te-IN": {
        "label": "Telugu (తెలుగు)",
        "native": "తెలుగు",
        "default_speaker": "shubh",
        "flag": "🇮🇳",
    },
    "ta-IN": {
        "label": "Tamil (தமிழ்)",
        "native": "தமிழ்",
        "default_speaker": "shubh",
        "flag": "🇮🇳",
    },
}

API_URL_TTS = "https://api.sarvam.ai/text-to-speech"
API_URL_STT = "https://api.sarvam.ai/speech-to-text"
API_URL_TRANSLATE = "https://api.sarvam.ai/translate"


def load_env_file() -> None:
    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        try:
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())
        except Exception:
            pass


load_env_file()


def get_api_key(override_key: Optional[str] = None) -> str:
    if override_key and override_key.strip():
        return override_key.strip()
    return os.getenv("SARVAM_API_KEY", DEFAULT_API_KEY).strip()


def is_voice_enabled(api_key: Optional[str] = None) -> bool:
    key = get_api_key(api_key)
    return bool(key and key.startswith("sk_"))


def transcribe_audio(
    audio_data: bytes | io.BytesIO,
    language_code: str = "unknown",
    model: str = "saaras:v3",
    api_key: Optional[str] = None,
) -> Tuple[str, str]:
    key = get_api_key(api_key)
    if not key:
        raise ValueError("Sarvam AI API key is missing.")

    if isinstance(audio_data, io.BytesIO):
        raw_bytes = audio_data.getvalue()
    else:
        raw_bytes = audio_data

    headers = {"api-subscription-key": key}
    files = {"file": ("speech.wav", io.BytesIO(raw_bytes), "audio/wav")}
    data = {"language_code": language_code, "model": model}

    response = requests.post(
        API_URL_STT, headers=headers, files=files, data=data, timeout=45
    )
    if not response.ok:
        raise RuntimeError(f"STT failed ({response.status_code}): {response.text}")

    result = response.json()
    transcript = result.get("transcript", "").strip()
    detected_lang = result.get("language_code", language_code)
    return transcript, detected_lang


def synthesize_speech(
    text: str,
    language_code: str = "hi-IN",
    speaker: Optional[str] = None,
    pace: float = 1.0,
    api_key: Optional[str] = None,
) -> bytes:
    key = get_api_key(api_key)
    if not key:
        raise ValueError("Sarvam AI API key is missing.")

    lang_meta = SUPPORTED_LANGUAGES.get(language_code, {})
    chosen_speaker = speaker or lang_meta.get("default_speaker", "shubh")

    headers = {
        "api-subscription-key": key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text[:2400],
        "language_code": language_code,
        "speaker": chosen_speaker,
        "model": "bulbul:v3",
        "pace": pace,
    }

    response = requests.post(API_URL_TTS, json=payload, headers=headers, timeout=45)
    if not response.ok:
        raise RuntimeError(f"TTS failed ({response.status_code}): {response.text}")

    data = response.json()
    audios = data.get("audios", [])
    if not audios:
        raise RuntimeError("TTS response returned no audio data.")

    return base64.b64decode(audios[0])


def translate_text(
    text: str,
    target_language_code: str = "hi-IN",
    source_language_code: str = "en-IN",
    api_key: Optional[str] = None,
) -> str:
    if target_language_code == source_language_code or not text.strip():
        return text

    key = get_api_key(api_key)
    if not key:
        return text

    headers = {
        "api-subscription-key": key,
        "Content-Type": "application/json",
    }
    payload = {
        "input": text[:1800],
        "source_language_code": source_language_code,
        "target_language_code": target_language_code,
        "model": "mayura:v1",
    }

    try:
        response = requests.post(
            API_URL_TRANSLATE, json=payload, headers=headers, timeout=30
        )
        if response.ok:
            return response.json().get("translated_text", text)
    except Exception:
        pass
    return text
