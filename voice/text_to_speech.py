"""
voice/text_to_speech.py
────────────────────────
Text-to-speech for REVIA.
Uses Microsoft Edge Neural TTS (100% Free, human-like quality, zero config):
  - Tunisian Arabic: ar-TN-HediNeural (supports Tunisian Darija & MSA)
  - French:          fr-FR-VivienneMultilingualNeural
  - English:         en-US-JennyNeural
Optionally uses ElevenLabs if ELEVENLABS_API_KEY is configured.
Falls back to pyttsx3 if offline.
"""

import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
import re
import io
import time
import asyncio
import tempfile
import threading
from dotenv import load_dotenv

load_dotenv()

ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# ── Voice mapping ─────────────────────────────────────────────────────────────
VOICE_MAP = {
    "french":  "fr-FR-VivienneMultilingualNeural",      # Natural, expressive French
    "english": "en-US-JennyNeural",                     # Expressive, natural English
}

# ── pyttsx3 fallback instance ─────────────────────────────────────────────────
_engine = None

def _get_engine():
    global _engine
    if _engine is None:
        try:
            import pyttsx3
            _engine = pyttsx3.init()
            _engine.setProperty("rate", 150)
            _engine.setProperty("volume", 0.9)
        except Exception:
            _engine = None
    return _engine


def _is_valid_key(key: str | None) -> bool:
    if not key:
        return False
    k = key.strip().lower()
    return not (k.startswith("your_") or "placeholder" in k or k == "")


def _clean_text_for_speech(text: str) -> str:
    """Strip markdown symbols, urls, and emojis so voice sounds clean and natural."""
    if not text:
        return ""
    # Remove code blocks
    cleaned = re.sub(r'```[\s\S]*?```', '', text)
    cleaned = re.sub(r'`[^`]*`', '', cleaned)
    # Remove markdown links [text](url) -> text
    cleaned = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', cleaned)
    # Remove headers, bullets, asterisks
    cleaned = re.sub(r'[#*_~`>]', '', cleaned)
    # Remove urls
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    # Collapse extra whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _detect_tts_voice(text: str) -> str:
    """Detect whether text is French or English to select the right neural voice."""
    try:
        from core.language import is_french
        if is_french(text):
            return VOICE_MAP["french"]
    except Exception:
        pass
    return VOICE_MAP["english"]


def speak(text: str, blocking: bool = False):
    """
    Speak the given text aloud using natural neural TTS.
    Automatically detects Arabic (Tunisian), French, or English.

    Args:
        text:     The text to speak.
        blocking: If True, wait until speaking finishes. Default: non-blocking.
    """
    cleaned = _clean_text_for_speech(text)
    if not cleaned:
        return

    # ElevenLabs override if valid key configured
    if _is_valid_key(ELEVENLABS_KEY):
        if blocking:
            _speak_elevenlabs(cleaned)
        else:
            threading.Thread(target=_speak_elevenlabs, args=(cleaned,), daemon=True).start()
        return

    # Default: Edge Neural TTS (Free, high-quality, native Tunisian Arabic)
    if blocking:
        _speak_edge_tts(cleaned)
    else:
        threading.Thread(target=_speak_edge_tts, args=(cleaned,), daemon=True).start()


def _speak_edge_tts(text: str):
    """Generate audio via edge-tts and play it through pygame.mixer."""
    voice = _detect_tts_voice(text)
    tmp_path = None

    try:
        import edge_tts
        import pygame

        async def _generate(path):
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(path)

        fd, tmp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)

        _stop_event.clear()
        asyncio.run(_generate(tmp_path))

        if _stop_event.is_set():
            return

        # Play with pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()

        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            if _stop_event.is_set():
                pygame.mixer.music.stop()
                break
            time.sleep(0.05)

    except Exception as e:
        if not _stop_event.is_set():
            print(f"[Voice] Edge TTS failed: {e}, falling back to pyttsx3...")
            _speak_pyttsx3_fallback(text)

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


_stop_event = threading.Event()

def is_speaking() -> bool:
    """Return True if audio playback is actively playing."""
    try:
        import pygame
        if pygame.mixer.get_init():
            return pygame.mixer.music.get_busy()
    except Exception:
        pass
    return False


def stop_speaking():
    """Stop any ongoing speech immediately."""
    _stop_event.set()
    try:
        import pygame
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
    except Exception:
        pass

    try:
        if _engine:
            _engine.stop()
    except Exception:
        pass


def set_speed(rate: int = 150):
    """Set speaking speed for pyttsx3."""
    engine = _get_engine()
    if engine:
        engine.setProperty("rate", rate)


# ── ElevenLabs (optional) ─────────────────────────────────────────────────────

def _speak_elevenlabs(text: str):
    """Use ElevenLabs API for natural-sounding voice if configured."""
    try:
        import requests
        import pygame

        voice_id = "21m00Tcm4TlvDq8ikWAM"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key":   ELEVENLABS_KEY,
            "Content-Type": "application/json",
        }
        body = {
            "text":          text,
            "model_id":      "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        resp = requests.post(url, json=body, headers=headers, timeout=15)
        if resp.status_code == 200:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(io.BytesIO(resp.content))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
        else:
            _speak_edge_tts(text)
    except Exception:
        _speak_edge_tts(text)

