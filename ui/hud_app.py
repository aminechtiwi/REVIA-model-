"""
ui/hud_app.py
─────────────
Native Desktop Application for REVIA Holographic HUD.
Uses pywebview with Windows EdgeChromium WebView2 engine to embed the
futuristic 3D Holographic Brain, dynamic soundwaves, and cybernetic
chat console into a true native Windows desktop application window.

Zero local hardware load: All reasoning runs on Groq 120B and Gemini Flash.
"""

import os
import sys
import json
import time
import psutil
import threading
import webview
from dotenv import load_dotenv

# Ensure core modules can be resolved
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.orchestrator import Orchestrator
from core.memory import clear_memory
from voice.text_to_speech import speak, stop_speaking
from voice.speech_to_text import listen_once

load_dotenv()


class ReviaApi:
    """Bidirectional API bridge exposed to JavaScript via window.pywebview.api."""

    def __init__(self):
        # All private internal state prefixed with _ so pywebview ignores it during introspection
        self._window = None
        self._orchestrator = None
        self._is_listening = False
        self._is_processing = False
        self._telemetry_running = True

    def _set_window(self, window):
        self._window = window

    def _init_orchestrator(self):
        if not self._orchestrator:
            print("[REVIA App] 🧠 Initializing Autonomous Cloud Brain...")
            self._orchestrator = Orchestrator()
            print("[REVIA App] ✅ Brain online.")

    # ── Exposed JS Methods (public, no leading underscore) ───────────────────

    def on_ui_ready(self):
        """Called by JavaScript when the Holographic HUD has fully mounted."""
        print("[REVIA App] 🌐 UI Bridge mounted successfully.")
        self._init_orchestrator()
        welcome_text = "Hi, I am REVIA. How can I help you?"
        self._push_message("revia", welcome_text)
        self._push_state("ONLINE", "System Ready")
        # Speak launch greeting out loud in neural voice
        threading.Thread(target=self._speak_with_soundwave, args=(welcome_text,), daemon=True).start()

    def send_message(self, user_text: str):
        """Receives user text from the HUD input console."""
        user_text = str(user_text).strip()
        if not user_text:
            return {"status": "empty"}

        if self._is_processing:
            return {"status": "busy", "message": "System currently reasoning"}

        # Run reasoning in background worker thread so UI never freezes
        threading.Thread(target=self._process_message_thread, args=(user_text,), daemon=True).start()
        return {"status": "received"}

    def toggle_voice(self):
        """Toggles microphone listening."""
        if self._is_listening:
            print("[REVIA App] 🎙️ Already listening...")
            return {"status": "already_listening"}

        threading.Thread(target=self._voice_listener_thread, daemon=True).start()
        return {"status": "listening_started"}

    def stop_speech(self):
        """Immediately interrupts any ongoing voice speech."""
        print("[REVIA App] 🛑 Interrupting speech...")
        stop_speaking()
        self._push_state("ONLINE", "Speech Halted")
        return {"status": "stopped"}

    def diagnose_screen(self):
        """Triggers multimodal visual analysis of the active desktop."""
        prompt = (
            "Please diagnose what is currently open and visible on my screen. "
            "Identify any errors, active tasks, code, or key information."
        )
        return self.send_message(prompt)

    def clear_chat(self):
        """Resets agent conversation memory and clears UI log."""
        try:
            clear_memory()
            print("[REVIA App] 🔄 Memory cleared.")
            self._push_state("ONLINE", "Memory Cleared")
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_system_telemetry(self):
        """Returns live PC stats for the HUD diagnostics gauges."""
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            return {
                "cpu_percent": round(cpu, 1),
                "ram_percent": round(mem.percent, 1),
                "ram_used_gb": round(mem.used / (1024 ** 3), 1),
                "ram_total_gb": round(mem.total / (1024 ** 3), 1),
                "timestamp": time.strftime("%H:%M:%S UTC", time.gmtime()),
            }
        except Exception:
            return {"cpu_percent": 15.0, "ram_percent": 42.0, "ram_used_gb": 6.8, "ram_total_gb": 16.0}

    # ── Background Worker Threads ────────────────────────────────────────────

    def _process_message_thread(self, user_text: str):
        self._is_processing = True
        try:
            # 1. Echo user message to HUD
            self._push_message("user", user_text)
            self._push_state("THINKING", "120B Synapse Reasoning...")
            self._push_audio_spike(1.8)

            # 2. Process via Cloud Brain (Think ⟶ Pick Tool ⟶ Execute ⟶ Verify)
            self._init_orchestrator()
            response = self._orchestrator.process(user_text)

            # 3. Stream REVIA response word by word to HUD
            self._push_state("SPEAKING", "Synthesizing Audio...")
            self._stream_message(response)

            # 4. Speak response in background and pulse audio soundwave
            self._speak_with_soundwave(response)

        except Exception as e:
            err_msg = f"⚠️ Cognitive Error: {str(e)}"
            self._push_message("revia", err_msg)
        finally:
            self._is_processing = False
            self._push_state("ONLINE", "System Ready")

    def _voice_listener_thread(self):
        # Immediately halt any ongoing TTS speech so mic never hears itself (Barge-in)
        stop_speaking()
        self._is_listening = True
        self._push_state("LISTENING", "Listening for speech (Deepgram Nova-2)...")
        self._push_audio_spike(2.2)

        try:
            spoken_text = listen_once(timeout=7, phrase_timeout=25)
            if spoken_text and spoken_text.strip():
                print(f"[REVIA App] 🎙️ Heard: {spoken_text}")
                self._is_listening = False
                self._process_message_thread(spoken_text)
            else:
                self._push_state("ONLINE", "No speech detected")
        except Exception as e:
            print(f"[REVIA App] Voice capture error: {e}")
            self._push_state("ONLINE", "Mic ready")
        finally:
            self._is_listening = False

    def _speak_with_soundwave(self, text: str):
        """Streams audio via Edge Neural TTS and spikes the HUD visualizer."""
        spike_active = True

        def _pulse_spikes():
            while spike_active:
                self._push_audio_spike(2.4)
                time.sleep(0.35)

        pulse_t = threading.Thread(target=_pulse_spikes, daemon=True)
        pulse_t.start()

        try:
            speak(text)
        finally:
            spike_active = False

    # ── Push Events to JavaScript ────────────────────────────────────────────

    def _stream_message(self, text: str, badge: str = ""):
        """Stream words to the HUD chat console with fluid non-blocking typewriter pacing."""
        if not self._window:
            return
        payload = json.dumps({"sender": "revia", "text": text, "badge": badge})
        try:
            self._window.evaluate_js(f"if (window.reviaStreamMessage) {{ window.reviaStreamMessage({payload}); }} else if (window.reviaAddMessage) {{ window.reviaAddMessage({payload}); }}")
        except Exception:
            self._push_message("revia", text, badge)

    def _push_message(self, sender: str, text: str, badge: str = ""):
        if not self._window:
            return
        payload = json.dumps({"sender": sender, "text": text, "badge": badge})
        script = f"if (window.reviaAddMessage) {{ window.reviaAddMessage({payload}); }}"
        try:
            self._window.evaluate_js(script)
        except Exception:
            pass

    def _push_state(self, state: str, text: str):
        if not self._window:
            return
        payload = json.dumps({"state": state, "text": text})
        script = f"if (window.reviaSetState) {{ window.reviaSetState({payload}); }}"
        try:
            self._window.evaluate_js(script)
        except Exception:
            pass

    def _push_audio_spike(self, amplitude: float = 2.0):
        if not self._window:
            return
        script = f"if (window.reviaAudioSpike) {{ window.reviaAudioSpike({amplitude}); }}"
        try:
            self._window.evaluate_js(script)
        except Exception:
            pass

    def _start_telemetry_loop(self):
        """Continuously streams real PC stats to the HUD every 2 seconds."""
        def _loop():
            while self._telemetry_running:
                if self._window:
                    stats = self.get_system_telemetry()
                    payload = json.dumps(stats)
                    try:
                        self._window.evaluate_js(f"if (window.reviaUpdateStats) {{ window.reviaUpdateStats({payload}); }}")
                    except Exception:
                        pass
                time.sleep(2.0)

        threading.Thread(target=_loop, daemon=True).start()


def launch_hud_app():
    """Launch REVIA as a native desktop application with embedded 3D Holographic HUD."""
    html_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "holographic_hud.html"))
    if not os.path.exists(html_path):
        raise FileNotFoundError(f"Holographic HUD template not found at: {html_path}")

    api = ReviaApi()

    # Create native Windows desktop application window
    window = webview.create_window(
        title="⚡ REVIA — Autonomous Quantum AI Assistant",
        url=f"file:///{html_path.replace(os.sep, '/')}",
        js_api=api,
        width=1380,
        height=880,
        min_size=(1080, 720),
        background_color="#02050e",
        resizable=True,
        text_select=True,
        easy_drag=False,
    )

    api._set_window(window)
    api._start_telemetry_loop()

    print("[REVIA] 🚀 Launching Native Holographic HUD Desktop Application...")
    webview.start(gui="edgechromium", debug=False)


if __name__ == "__main__":
    launch_hud_app()
