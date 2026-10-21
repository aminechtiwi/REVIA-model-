# ⚡ REVIA — Autonomous Quantum AI Assistant

An autonomous desktop AI assistant featuring a 3D Holographic Brain HUD, neural voice duplexing, multimodal screen analysis, parallel multi-model cloud brain, and automated PC control.

---

## 🚀 Quick Start

### Step 1 — Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### Step 2 — Configure API Keys
Copy the example file to `.env`:
```bash
copy .env.example .env
```
Open `.env` and fill in your keys:
- **GROQ_API_KEY** → [console.groq.com/keys](https://console.groq.com/keys) (Free & ultra-fast)
- **GEMINI_API_KEY** → [aistudio.google.com](https://aistudio.google.com) (Free tier with Vision)
- **OPENROUTER_API_KEY** → [openrouter.ai/keys](https://openrouter.ai/keys) (Free reasoning models)
- **OPENAI_API_KEY** / **ANTHROPIC_API_KEY** → (Optional)

> **Note:** Only **at least ONE key** (e.g. Groq or Gemini) is needed to start.

### Step 3 — Verify Installation
```bash
python main.py --check
```

### Step 4 — Run REVIA
```bash
python main.py          # 3D Holographic HUD Native Desktop App (Recommended)
python main.py --text   # Lightweight Terminal Text Mode
python main.py --classic # Legacy Tkinter GUI
```

---

## 🗣️ What REVIA Can Do

| Capability | Example Prompt | Description |
|---|---|---|
| **Autonomous Job Search** | `search jobs for python developer in Tunisia` | Launches browser and scans LinkedIn for matching roles |
| **Email & Calendar** | `check my gmail`, `check my calendar` | Scans emails or upcoming events via Google APIs |
| **Desktop Automation** | `open chrome`, `open notepad` | Launches applications with safety confirmation guardrails |
| **Vision Diagnostics** | `I have a problem on my screen` | Captures active display and diagnoses errors with multimodal AI |
| **System Diagnostics** | `what's my PC status` | Live CPU, RAM, disk telemetry in real-time |
| **Deep Research** | `research quantum computing breakthroughs` | Multi-step deep web search and synthesized insights |
| **Multilingual Voice** | `kifech naawen?`, `bonjour`, `hello` | Supports English, French, Standard Arabic, and Tunisian Arabic 🇹🇳 |

---

## 📁 Project Architecture

```
revia/
├── main.py                     ← Entry point (--hud, --text, --classic, --check)
├── requirements.txt
├── .env.example                ← Environment template (never commit .env!)
├── core/
│   ├── orchestrator.py         ← Central cognitive engine & tool dispatch
│   ├── router.py               ← Multi-model parallel routing & fallback
│   ├── language.py             ← Arabic / French / English detection & prompt tuning
│   └── memory.py               ← SQLite persistent conversation memory
├── tools/
│   ├── pc_control.py           ← System commands & app launcher
│   ├── browser_agent.py        ← Playwright browser automation
│   ├── problem_detector.py     ← Multimodal screen capture & diagnostics
│   ├── search.py               ← Web search integration
│   └── deep_search.py          ← Multi-source iterative research
├── voice/
│   ├── speech_to_text.py       ← Deepgram Nova-2 / Whisper STT with barge-in
│   └── text_to_speech.py       ← Microsoft Edge Neural TTS
├── ui/
│   ├── hud_app.py              ← Native pywebview desktop wrapper
│   ├── holographic_hud.html    ← 3D Three.js Holographic Brain & HUD console
│   ├── revia_boot.html         ← Cybernetic boot sequence screen
│   └── chat_window.py          ← Fallback Tkinter desktop interface
└── config/
    ├── settings.json           ← App configuration & app/website paths
    └── knowledge_faq.json      ← Local system knowledge base
```

---

## 🔒 Security & Privacy

- `.env` contains your private API credentials and is excluded via `.gitignore`.
- REVIA asks for user confirmation before launching desktop applications or executing system actions.
