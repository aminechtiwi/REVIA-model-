"""
voice/speech_to_text.py
────────────────────────
Speech recognition for Jarvis.
Listens to microphone and converts speech to text.

Two modes:
  1. SpeechRecognition (Google API — free, easy, fast)
  2. Whisper (OpenAI — higher accuracy, supports Tunisian Arabic)
"""

import os
import sys
import json
import time
import asyncio
import requests
import speech_recognition as sr
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
GROQ_API_KEY     = os.getenv("GROQ_API_KEY", "")

# ── Recognizer instance (Fallback only) ────────────────────────────────────────
_recognizer  = sr.Recognizer()
_recognizer.energy_threshold    = 300   # Balanced sensitivity so words aren't cut off
_recognizer.dynamic_energy_threshold = True
_recognizer.pause_threshold     = 2.0   # Generous 2.0s pause tolerance (no premature cutoff)

# Common Whisper hallucinations triggered by empty room noise / silence
HALLUCINATIONS = {
    "thank you", "thank you.", "thank you!", "thank you very much",
    "thank you for watching", "thanks for watching", "thanks for watching.",
    "thank you so much", "thank you so much.", "merci", "merci.",
    "subtitles by", "subtitles by the amara.org community",
    "you", "bye", "bye.", "peace", "thanks", "thanks.", "watching"
}

def _is_hallucination(text: str) -> bool:
    if not text:
        return True
    clean = text.strip().lower().rstrip("!.,? ")
    return clean in HALLUCINATIONS or any(h in clean for h in ["thank you for watching", "subtitles by", "amara.org"])


async def _async_deepgram_stream(timeout: int = 6, max_duration: int = 25) -> str | None:
    """
    Stream live microphone audio to Deepgram Nova-2 over WebSocket.
    Uses Deepgram's neural acoustic + language endpointer (Alexa-grade turn taking)
    so you are never interrupted while thinking or pausing mid-sentence.
    """
    import pyaudio
    import websockets

    key = os.getenv("DEEPGRAM_API_KEY", "")
    if not _is_valid_key(key):
        return None

    url = (
        "wss://api.deepgram.com/v1/listen?"
        "model=nova-2&smart_format=true&encoding=linear16&sample_rate=16000&channels=1"
        "&endpointing=600&interim_results=true&utterance_end_ms=1500&vad_events=true"
    )
    headers = {"Authorization": f"Token {key}"}

    p = pyaudio.PyAudio()
    stream = None
    transcript_parts = []
    speech_detected = False
    stop_event = asyncio.Event()

    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1024
        )
    except Exception as e:
        print(f"[Voice] Could not open PyAudio stream: {e}")
        p.terminate()
        return None

    try:
        async with websockets.connect(url, additional_headers=headers) as ws:
            print("[Voice] 🎤 Deepgram Nova-2 streaming connected (Alexa-grade turn-taking)...")

            async def mic_sender():
                nonlocal speech_detected
                start_time = time.time()
                while not stop_event.is_set():
                    elapsed = time.time() - start_time
                    if elapsed > max_duration:
                        break
                    # If silence exceeds timeout before speech starts, exit
                    if not speech_detected and elapsed > timeout:
                        break

                    try:
                        data = stream.read(1024, exception_on_overflow=False)
                        await ws.send(data)
                        await asyncio.sleep(0.005)
                    except Exception:
                        break

                try:
                    await ws.send(json.dumps({"type": "CloseStream"}))
                except Exception:
                    pass

            async def transcript_receiver():
                nonlocal speech_detected
                async for message in ws:
                    try:
                        res = json.loads(message)
                        msg_type = res.get("type")

                        if msg_type == "SpeechStarted":
                            speech_detected = True

                        elif msg_type == "Results":
                            alt = res.get("channel", {}).get("alternatives", [{}])[0]
                            text = alt.get("transcript", "").strip()
                            is_final = res.get("is_final", False)
                            speech_final = res.get("speech_final", False)

                            if text:
                                speech_detected = True

                            if is_final and text:
                                transcript_parts.append(text)
                                print(f"[Voice] Deepgram heard: {text}")

                            # Deepgram neural endpointer determined speech is complete
                            if speech_final and transcript_parts:
                                stop_event.set()
                                break

                        elif msg_type == "UtteranceEnd":
                            if transcript_parts:
                                stop_event.set()
                                break

                        elif msg_type == "Metadata":
                            break

                    except Exception:
                        continue

            await asyncio.gather(mic_sender(), transcript_receiver())

    except Exception as e:
        print(f"[Voice] Deepgram WebSocket error: {e}")
    finally:
        if stream:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        p.terminate()

    full_text = " ".join(transcript_parts).strip()
    return full_text if full_text and not _is_hallucination(full_text) else None


def listen_deepgram_streaming(timeout: int = 6, max_duration: int = 25) -> str | None:
    """Synchronous wrapper around _async_deepgram_stream."""
    try:
        return asyncio.run(_async_deepgram_stream(timeout=timeout, max_duration=max_duration))
    except Exception as e:
        print(f"[Voice] Deepgram streaming runner error: {e}")
        return None


def _transcribe_deepgram(audio: sr.AudioData) -> str | None:
    """Use Deepgram Nova-2 REST API to transcribe recorded audio buffers."""
    key = os.getenv("DEEPGRAM_API_KEY", "")
    if not _is_valid_key(key):
        return None

    try:
        wav_bytes = audio.get_wav_data()
        url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true"
        headers = {
            "Authorization": f"Token {key}",
            "Content-Type": "audio/wav"
        }
        resp = requests.post(url, headers=headers, data=wav_bytes, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            channels = data.get("results", {}).get("channels", [])
            if channels:
                alt = channels[0].get("alternatives", [{}])[0]
                text = alt.get("transcript", "").strip()
                if text and not _is_hallucination(text):
                    print(f"[Voice] Deepgram Nova-2 heard: {text}")
                    return text
        else:
            print(f"[Voice] Deepgram REST error ({resp.status_code}): {resp.text[:100]}")
    except Exception as e:
        print(f"[Voice] Deepgram REST exception: {e}")
    return None


def listen_once(timeout: int = 6, phrase_timeout: int = 15) -> str | None:
    """
    Listen to the microphone and return transcribed text.
    1. Uses Deepgram Nova-2 real-time streaming with neural turn-taking.
    2. Falls back to SpeechRecognition with a generous 2.0s pause threshold.
    """
    # 1. Try Deepgram Streaming with Neural Turn-Taking (No pause cutoffs)
    if _is_valid_key(DEEPGRAM_API_KEY):
        try:
            result = listen_deepgram_streaming(timeout=timeout, max_duration=phrase_timeout)
            if result:
                return result
        except Exception as e:
            print(f"[Voice] Deepgram streaming failed, falling back to batch recording: {e}")

    # 2. Fallback: Batch recording with generous 2.0s pause threshold
    with sr.Microphone() as source:
        print("[Voice] 🎤 Listening (batch fallback)...")
        _recognizer.adjust_for_ambient_noise(source, duration=0.3)
        try:
            audio = _recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_timeout)
        except sr.WaitTimeoutError:
            print("[Voice] ⏱ No speech detected.")
            return None

    return _transcribe(audio)


def _is_valid_key(key: str | None) -> bool:
    """Check if key is non-empty and not a placeholder."""
    if not key:
        return False
    k = key.strip().lower()
    return not (k.startswith("your_") or "placeholder" in k or k == "")


def _transcribe(audio: sr.AudioData) -> str | None:
    """
    Transcribe audio using the best available method:
    1. Deepgram Nova-2 (Highest accuracy, smart formatting)
    2. Groq Whisper Large v3
    3. Google STT (Free fallback)
    4. OpenAI Whisper
    """
    # 1. Deepgram Nova-2
    if _is_valid_key(DEEPGRAM_API_KEY):
        result = _transcribe_deepgram(audio)
        if result:
            return result

    # 2. Groq Whisper
    if _is_valid_key(GROQ_API_KEY):
        result = _transcribe_groq_whisper(audio)
        if result:
            return result

    # 3. Google STT
    result = _transcribe_google(audio)
    if result:
        return result

    # 4. Fallback to OpenAI Whisper API
    if _is_valid_key(OPENAI_API_KEY):
        result = _transcribe_whisper_api(audio)
        if result:
            return result

    return None


def _transcribe_google(audio: sr.AudioData) -> str | None:
    """Free Google STT — prioritizing Tunisian Arabic so words aren't forced into English."""
    lang_pref = os.getenv("REVIA_DEFAULT_LANGUAGE", os.getenv("JARVIS_DEFAULT_LANGUAGE", "auto")).lower()
    
    if lang_pref == "french":
        language_order = ["fr-FR", "en-US"]
    else:
        language_order = ["en-US", "fr-FR"]

    for lang in language_order:
        try:
            text = _recognizer.recognize_google(audio, language=lang)
            if text and not _is_hallucination(text):
                print(f"[Voice] Google heard ({lang}): {text}")
                return text
        except sr.UnknownValueError:
            continue
        except sr.RequestError as e:
            print(f"[Voice] Google STT network error: {e}")
            return None

    print("[Voice] Could not understand audio.")
    return None


def _transcribe_groq_whisper(audio: sr.AudioData) -> str | None:
    """
    Use Groq Whisper API (whisper-large-v3-turbo) — Free & ultra-fast.
    Supports English and French.
    """
    try:
        import openai
        import io

        wav_bytes = audio.get_wav_data()
        audio_file = io.BytesIO(wav_bytes)
        audio_file.name = "audio.wav"

        client = openai.OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=GROQ_API_KEY
        )
        transcript = client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=audio_file,
            prompt="English, French speech. Clear transcription.",
            temperature=0.0,
        )
        text = transcript.text.strip()
        if _is_hallucination(text):
            return None
        print(f"[Voice] Groq Whisper heard: {text}")
        return text

    except Exception as e:
        print(f"[Voice] Groq Whisper error: {e}")
        return None


def _transcribe_whisper_api(audio: sr.AudioData) -> str | None:
    """
    Use OpenAI Whisper API — best accuracy for Tunisian Arabic / mixed language.
    Costs ~$0.006/minute.
    """
    try:
        import openai
        import io
        import wave

        # Convert AudioData to WAV bytes
        wav_bytes = audio.get_wav_data()
        audio_file = io.BytesIO(wav_bytes)
        audio_file.name = "audio.wav"

        client      = openai.OpenAI(api_key=OPENAI_API_KEY)
        transcript  = client.audio.transcriptions.create(
            model    = "whisper-1",
            file     = audio_file,
            language = None,  # Auto-detect language (handles Tunisian Arabic)
        )
        text = transcript.text.strip()
        if _is_hallucination(text):
            return None
        print(f"[Voice] Whisper heard: {text}")
        return text

    except Exception as e:
        print(f"[Voice] Whisper API error: {e}")
        return None


def start_continuous_listen(callback):
    """
    Start continuous background listening.
    Calls callback(text) whenever speech is recognized.

    Args:
        callback: Function to call with the transcribed text.

    Returns:
        stop_fn: Call this function to stop listening.
    """
    def handle_audio(recognizer, audio):
        text = _transcribe(audio)
        if text and not _is_hallucination(text):
            callback(text)

    stop_fn = _recognizer.listen_in_background(
        sr.Microphone(),
        handle_audio,
        phrase_time_limit=15
    )
    print("[Voice] 🎤 Continuous listening started. Call stop_fn() to stop.")
    return stop_fn
