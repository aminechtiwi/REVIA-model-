"""
ui/chat_window.py
──────────────────
Jarvis desktop GUI — dark themed Tkinter chat window.

Features:
  - Chat history with colored bubbles (user / Jarvis)
  - Text input + send button
  - Voice button (toggle mic)
  - System status bar
  - Minimize to system tray (optional)
"""

import tkinter as tk
from tkinter import scrolledtext, font
import threading
import queue
import os
import sys
import time

# ── Color palette ─────────────────────────────────────────────────────────────
COLORS = {
    "bg":           "#1a1a2e",   # Dark navy background
    "sidebar":      "#16213e",   # Slightly lighter sidebar
    "user_bubble":  "#0f3460",   # User message bubble
    "ai_bubble":    "#533483",   # Jarvis message bubble
    "text":         "#e0e0e0",   # Default text
    "text_dim":     "#888888",   # Dimmed text
    "accent":       "#e94560",   # Red accent (Jarvis eye color)
    "green":        "#00d084",   # Success color
    "input_bg":     "#0d0d1a",   # Input field background
    "button":       "#e94560",   # Button color
    "button_hover": "#c73652",   # Button hover
}

FONT_FAMILY = "Segoe UI"


class JarvisGUI:
    def __init__(self, orchestrator):
        self.orchestrator    = orchestrator
        self.response_queue  = queue.Queue()
        self.is_listening    = False
        self.stop_listen_fn  = None

        self._build_window()
        self._start_response_poller()

    # ── Window Construction ────────────────────────────────────────────────────

    def _build_window(self):
        self.root = tk.Tk()
        self.root.title("⚡ REVIA — Personal AI Assistant")
        self.root.geometry("900x680")
        self.root.configure(bg=COLORS["bg"])
        self.root.resizable(True, True)

        # Icon (optional)
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "..", "config", "revia_icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        self._build_header()
        self._build_chat_area()
        self._build_input_area()
        self._build_status_bar()

        # Welcome message
        self._add_message("revia",
            "Hello! I am REVIA, your autonomous executive AI assistant. ⚡\n"
            "Bonjour ! Je suis REVIA, votre assistante IA exécutive.\n"
            "How can I help you today? / Comment puis-je vous aider aujourd'hui ?"
        )

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_header(self):
        header = tk.Frame(self.root, bg=COLORS["sidebar"], height=60)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)

        # Logo / name
        logo = tk.Label(header, text="⚡ REVIA",
                        fg=COLORS["accent"], bg=COLORS["sidebar"],
                        font=(FONT_FAMILY, 20, "bold"))
        logo.pack(side=tk.LEFT, padx=20, pady=10)

        subtitle = tk.Label(header, text="Personal AI Assistant",
                            fg=COLORS["text_dim"], bg=COLORS["sidebar"],
                            font=(FONT_FAMILY, 10))
        subtitle.pack(side=tk.LEFT, pady=10)

        # Clear button
        clear_btn = tk.Button(header, text="🗑 Clear",
                              command=self._clear_chat,
                              bg=COLORS["sidebar"], fg=COLORS["text_dim"],
                              relief=tk.FLAT, cursor="hand2",
                              font=(FONT_FAMILY, 9))
        clear_btn.pack(side=tk.RIGHT, padx=5)

        # 3D Holographic HUD Button
        hud_btn = tk.Button(header, text="🌐 3D Brain HUD",
                            command=self._open_holographic_hud,
                            bg="#0e2a4a", fg="#00f3ff",
                            activebackground="#00f3ff", activeforeground="#050a18",
                            relief=tk.FLAT, cursor="hand2",
                            font=(FONT_FAMILY, 9, "bold"), padx=8)
        hud_btn.pack(side=tk.RIGHT, padx=10)

        # Status indicator
        self.status_dot = tk.Label(header, text="●",
                                   fg=COLORS["green"], bg=COLORS["sidebar"],
                                   font=(FONT_FAMILY, 14))
        self.status_dot.pack(side=tk.RIGHT, padx=5)

    def _open_holographic_hud(self):
        """Open the interactive 3D Holographic Brain HUD in the default browser."""
        import webbrowser
        hud_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "holographic_hud.html"))
        webbrowser.open(f"file://{hud_path}")

    def _build_chat_area(self):
        chat_frame = tk.Frame(self.root, bg=COLORS["bg"])
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 0))

        # Scrollable text area
        self.chat_area = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            bg=COLORS["bg"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 11),
            relief=tk.FLAT,
            padx=15,
            pady=10,
            state=tk.DISABLED,
            cursor="arrow",
        )
        self.chat_area.pack(fill=tk.BOTH, expand=True)

        # Configure text tags for colored bubbles
        self.chat_area.tag_configure("user_name",
            foreground="#64b5f6", font=(FONT_FAMILY, 9, "bold"))
        self.chat_area.tag_configure("user_text",
            foreground=COLORS["text"], font=(FONT_FAMILY, 11),
            lmargin1=30, lmargin2=30)
        self.chat_area.tag_configure("revia_name",
            foreground=COLORS["accent"], font=(FONT_FAMILY, 9, "bold"))
        self.chat_area.tag_configure("revia_text",
            foreground="#e0e0e0", font=(FONT_FAMILY, 11),
            lmargin1=30, lmargin2=30)
        self.chat_area.tag_configure("dim",
            foreground=COLORS["text_dim"], font=(FONT_FAMILY, 8))
        self.chat_area.tag_configure("thinking",
            foreground="#888888", font=(FONT_FAMILY, 10, "italic"))

    def _build_input_area(self):
        input_frame = tk.Frame(self.root, bg=COLORS["sidebar"], pady=10)
        input_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=5)

        # Voice button
        self.voice_btn = tk.Button(
            input_frame,
            text="🎤",
            command=self._toggle_voice,
            bg=COLORS["sidebar"],
            fg=COLORS["text"],
            relief=tk.FLAT,
            font=(FONT_FAMILY, 16),
            cursor="hand2",
            width=3,
        )
        self.voice_btn.pack(side=tk.LEFT, padx=(10, 5))

        # Text input field
        self.input_var = tk.StringVar()
        self.input_field = tk.Entry(
            input_frame,
            textvariable=self.input_var,
            bg=COLORS["input_bg"],
            fg=COLORS["text"],
            font=(FONT_FAMILY, 12),
            relief=tk.FLAT,
            insertbackground=COLORS["accent"],
        )
        self.input_field.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=10, padx=5)
        self.input_field.bind("<Return>", lambda e: self._send_message())
        self.input_field.focus()

        # Stop button (interrupt speech & actions)
        self.stop_btn = tk.Button(
            input_frame,
            text="⏹ Stop",
            command=self._stop_speaking_action,
            bg="#2d1620",
            fg=COLORS["accent"],
            activebackground=COLORS["accent"],
            activeforeground="white",
            relief=tk.FLAT,
            font=(FONT_FAMILY, 10, "bold"),
            cursor="hand2",
            padx=10,
            pady=5,
        )
        self.stop_btn.pack(side=tk.RIGHT, padx=5)

        # Send button
        self.send_btn = tk.Button(
            input_frame,
            text="Send ➤",
            command=self._send_message,
            bg=COLORS["button"],
            fg="white",
            relief=tk.FLAT,
            font=(FONT_FAMILY, 11, "bold"),
            cursor="hand2",
            padx=15,
            pady=5,
        )
        self.send_btn.pack(side=tk.RIGHT, padx=(5, 10))

        # Hotkey: Press Escape to stop REVIA immediately
        self.root.bind("<Escape>", lambda e: self._stop_speaking_action())

    def _build_status_bar(self):
        self.status_label = tk.Label(
            self.root,
            text="Ready",
            fg=COLORS["text_dim"],
            bg=COLORS["bg"],
            font=(FONT_FAMILY, 8),
            anchor=tk.W,
        )
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=2)

    # ── Message Handling ───────────────────────────────────────────────────────

    def _add_message(self, sender: str, text: str):
        """Add a message bubble to the chat area."""
        self.chat_area.configure(state=tk.NORMAL)

        if sender == "user":
            self.chat_area.insert(tk.END, "\n  You\n", "user_name")
            self.chat_area.insert(tk.END, f"  {text}\n", "user_text")
        else:
            self.chat_area.insert(tk.END, "\n  ⚡ REVIA\n", "revia_name")
            self.chat_area.insert(tk.END, f"  {text}\n", "revia_text")

        self.chat_area.insert(tk.END, "\n", "dim")
        self.chat_area.configure(state=tk.DISABLED)
        self.chat_area.see(tk.END)

    def _add_thinking(self):
        """Show 'REVIA is thinking...' indicator."""
        self.chat_area.configure(state=tk.NORMAL)
        self.chat_area.insert(tk.END, "\n  ⚡ REVIA is thinking...\n", "thinking")
        self.chat_area.configure(state=tk.DISABLED)
        self.chat_area.see(tk.END)

    def _remove_thinking(self):
        """Remove the thinking indicator."""
        self.chat_area.configure(state=tk.NORMAL)
        content = self.chat_area.get("1.0", tk.END)
        if "REVIA is thinking..." in content:
            start = content.rfind("\n  ⚡ REVIA is thinking...\n")
            if start != -1:
                line_start = f"1.0 + {start} chars"
                line_end   = f"1.0 + {start + len(chr(10) + '  ⚡ REVIA is thinking...' + chr(10))} chars"
                self.chat_area.delete(line_start, line_end)
        self.chat_area.configure(state=tk.DISABLED)

    def _send_message(self):
        """Handle user sending a message with anti-duplicate guard."""
        text = self.input_var.get().strip()
        if not text:
            return

        now = time.time()
        last_text = getattr(self, "_last_sent_text", "")
        last_time = getattr(self, "_last_sent_time", 0.0)

        # Anti-duplicate: Discard if the exact same message was sent less than 4 seconds ago
        if text.lower() == last_text.lower() and (now - last_time) < 4.0:
            print(f"[REVIA] 🛡️ Ignored duplicate message: '{text}'")
            self.input_var.set("")
            return

        self._last_sent_text = text
        self._last_sent_time = now
        self._is_processing = True
        self.input_var.set("")
        self._add_message("user", text)
        self._set_status("Processing...", busy=True)
        self._add_thinking()

        # Run orchestrator in background thread to not freeze UI
        thread = threading.Thread(
            target=self._process_in_background,
            args=(text,),
            daemon=True,
        )
        thread.start()

    def _process_in_background(self, user_input: str):
        """Call orchestrator in a background thread."""
        try:
            response = self.orchestrator.process(user_input)
        except Exception as e:
            response = f"❌ Error: {e}"
        self.response_queue.put(response)

    def _start_response_poller(self):
        """Poll the response queue every 100ms to update UI."""
        try:
            response = self.response_queue.get_nowait()
            self._remove_thinking()
            self._add_message("revia", response)
            self._set_status("Ready")

            # Speak the response, then re-enable mic input
            def _speak_and_unlock():
                try:
                    from voice.text_to_speech import speak
                    speak(response, blocking=True)
                except Exception:
                    pass
                finally:
                    self._is_processing = False

            threading.Thread(target=_speak_and_unlock, daemon=True).start()

        except queue.Empty:
            pass

        self.root.after(100, self._start_response_poller)

    # ── Voice (Push-to-Talk: Click once to speak, auto-closes) ─────────────────

    def _toggle_voice(self):
        """Push-to-Talk: Click once to record, automatically turns off when you finish speaking."""
        if getattr(self, "_is_listening_single", False):
            # Already listening, clicking again cancels recording
            self._is_listening_single = False
            self.voice_btn.configure(fg=COLORS["text"], text="🎤")
            self._set_status("Ready")
            return

        # If REVIA is currently speaking, stop her first!
        try:
            from voice.text_to_speech import stop_speaking
            stop_speaking()
        except Exception:
            pass

        self._is_listening_single = True
        self.voice_btn.configure(fg=COLORS["accent"], text="🔴")
        self._set_status("🎤 Listening... Speak now")

        def _record_thread():
            try:
                from voice.speech_to_text import listen_once
                text = listen_once(timeout=6, phrase_timeout=12)
                if text and self._is_listening_single:
                    self.root.after(0, lambda: self._on_voice_input(text))
            except Exception as e:
                self.root.after(0, lambda: self._add_message("revia", f"❌ Mic error: {e}"))
            finally:
                self._is_listening_single = False
                self.root.after(0, lambda: self.voice_btn.configure(fg=COLORS["text"], text="🎤"))
                if not getattr(self, "_is_processing", False):
                    self.root.after(0, lambda: self._set_status("Ready"))

        threading.Thread(target=_record_thread, daemon=True).start()

    def _stop_voice(self):
        """Cancel recording immediately."""
        self._is_listening_single = False
        self.voice_btn.configure(fg=COLORS["text"], text="🎤")
        self._set_status("Ready")

    def _stop_speaking_action(self):
        """Immediately stop speaking and reset to Ready."""
        try:
            from voice.text_to_speech import stop_speaking
            stop_speaking()
        except Exception:
            pass
        self._is_processing = False
        self._remove_thinking()
        self._set_status("Ready")

    def _on_voice_input(self, text: str):
        """Called when voice recognition captures text. Supports live barge-in interruption."""
        if not text or not text.strip():
            return

        # If REVIA is currently speaking or processing, immediately stop her and take the new question!
        try:
            from voice.text_to_speech import is_speaking, stop_speaking
            if is_speaking() or getattr(self, "_is_processing", False):
                print(f"[REVIA] ✋ User spoke: '{text}'. Stopping speech & re-listening...")
                stop_speaking()
                self._is_processing = False
                self._remove_thinking()
        except Exception:
            pass

        self.input_var.set(text)
        self.root.after(0, self._send_message)

    # ── Utilities ──────────────────────────────────────────────────────────────

    def _set_status(self, message: str, busy: bool = False):
        self.status_label.configure(text=message)
        dot_color = COLORS["accent"] if busy else COLORS["green"]
        self.status_dot.configure(fg=dot_color)

    def _clear_chat(self):
        self.chat_area.configure(state=tk.NORMAL)
        self.chat_area.delete("1.0", tk.END)
        self.chat_area.configure(state=tk.DISABLED)
        from core.memory import clear_memory
        clear_memory()
        self._add_message("revia", "Memory cleared. Fresh start! 🔄")

    def _on_close(self):
        if self.is_listening:
            self._stop_voice()
        self.root.destroy()

    def run(self):
        """Start the GUI event loop."""
        self.root.mainloop()
