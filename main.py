"""
main.py
────────
Jarvis entry point. Run this file to start the assistant:

    python main.py

Options:
    python main.py --hud    → Launch 3D Holographic Brain HUD in browser
    python main.py --text   → Text-only mode (no GUI, use terminal)
    python main.py --check  → Check API keys and dependencies
"""

import sys
import os

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"

# Ensure UTF-8 output in Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure the project root is in the Python path
sys.path.insert(0, os.path.dirname(__file__))


def check_dependencies():
    """Check that all required packages and API keys are present."""
    print("=" * 50)
    print("  ⚡ REVIA — Dependency Check")
    print("=" * 50)

    # Check packages
    packages = {
        "litellm":         "pip install litellm",
        "langdetect":      "pip install langdetect",
        "pyautogui":       "pip install pyautogui",
        "psutil":          "pip install psutil",
        "PIL":             "pip install pillow",
        "speech_recognition": "pip install SpeechRecognition",
        "pyttsx3":         "pip install pyttsx3",
        "edge_tts":        "pip install edge-tts",
        "pygame":          "pip install pygame",
        "requests":        "pip install requests",
        "dotenv":          "pip install python-dotenv",
        "webview":         "pip install pywebview",
    }

    all_ok = True
    for pkg, install_cmd in packages.items():
        try:
            __import__(pkg)
            print(f"  ✅ {pkg}")
        except ImportError:
            print(f"  ❌ {pkg} — Run: {install_cmd}")
            all_ok = False

    # Check API keys
    print("\n  API Keys:")
    from dotenv import load_dotenv
    load_dotenv()

    keys = {
        "GROQ_API_KEY":      "100% Free at: https://console.groq.com/keys",
        "GEMINI_API_KEY":    "Free tier at: https://aistudio.google.com/app/apikey",
        "OPENROUTER_API_KEY":"Free models at: https://openrouter.ai/keys",
        "ANTHROPIC_API_KEY": "https://console.anthropic.com",
        "OPENAI_API_KEY":    "https://platform.openai.com",
    }

    any_key = False
    for key, url in keys.items():
        val = os.getenv(key, "")
        if val and val != f"your_{key.lower()}_here" and not val.startswith("your_"):
            print(f"  ✅ {key} is set")
            any_key = True
        else:
            print(f"  ⚠️  {key} not set — {url}")

    if not any_key:
        print("\n  ❌ No API keys found! Please set at least one in your .env file.")
        all_ok = False

    print("\n" + ("  ✅ All good! Ready to run REVIA." if all_ok else
                  "  ⚠️  Fix the issues above, then run: python main.py"))
    print("=" * 50)
    return all_ok


def run_native_hud():
    """Launch REVIA as a native desktop application with embedded 3D Holographic HUD."""
    print("[REVIA] 🚀 Launching Native Holographic HUD Desktop Application...")
    try:
        from ui.hud_app import launch_hud_app
        launch_hud_app()
    except Exception as e:
        print(f"[REVIA] ⚠️ Native HUD launch failed: {e}")
        print("[REVIA] 🔄 Falling back to Classic Desktop GUI...")
        run_classic_gui()


def run_classic_gui():
    """Launch REVIA with the legacy Tkinter desktop GUI."""
    print("[REVIA] Starting classic desktop GUI...")
    from core.orchestrator import Orchestrator
    from ui.chat_window    import JarvisGUI

    orchestrator = Orchestrator()
    gui          = JarvisGUI(orchestrator)
    gui.run()


def run_text_mode():
    """Launch REVIA in terminal text mode (no GUI)."""
    from colorama import Fore, Style, init
    init()

    from core.orchestrator import Orchestrator
    orchestrator = Orchestrator()

    print(f"\n{Fore.CYAN}{'='*50}")
    print(f"  ⚡ REVIA — Text Mode")
    print(f"  Type 'quit' to exit | 'clear' to reset memory")
    print(f"{'='*50}{Style.RESET_ALL}\n")

    while True:
        try:
            user_input = input(f"{Fore.BLUE}You:{Style.RESET_ALL} ").strip()

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "bye"):
                print(f"{Fore.CYAN}REVIA: Goodbye! Au revoir et à bientôt ! 👋{Style.RESET_ALL}")
                break
            if user_input.lower() == "clear":
                from core.memory import clear_memory
                clear_memory()
                print(f"{Fore.CYAN}REVIA: Memory cleared! 🔄{Style.RESET_ALL}\n")
                continue

            print(f"{Fore.YELLOW}REVIA is thinking...{Style.RESET_ALL}")
            response = orchestrator.process(user_input)
            print(f"{Fore.MAGENTA}⚡ REVIA:{Style.RESET_ALL} {response}\n")

        except KeyboardInterrupt:
            print(f"\n{Fore.CYAN}REVIA: Goodbye! Au revoir ! 👋{Style.RESET_ALL}")
            break
        except Exception as e:
            print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--check" in args:
        check_dependencies()
    elif "--text" in args:
        run_text_mode()
    elif "--classic" in args:
        run_classic_gui()
    else:
        # Default (and --hud): Native Holographic HUD Desktop Application
        from dotenv import load_dotenv
        load_dotenv()

        def _is_valid_key(val: str | None) -> bool:
            if not val:
                return False
            v = val.strip().lower()
            return not (v.startswith("your_") or "placeholder" in v or v == "")

        has_key = any([
            _is_valid_key(os.getenv("GROQ_API_KEY")),
            _is_valid_key(os.getenv("GEMINI_API_KEY")),
            _is_valid_key(os.getenv("OPENROUTER_API_KEY")),
            _is_valid_key(os.getenv("ZAI_API_KEY")),
            _is_valid_key(os.getenv("ANTHROPIC_API_KEY")),
            _is_valid_key(os.getenv("OPENAI_API_KEY")),
        ])

        if not has_key:
            print("\n❌ No valid API keys found in .env file!")
            print("   Please edit .env and provide at least one valid API key:")
            print("   - GROQ_API_KEY     -> 100% Free at: https://console.groq.com/keys (Recommended!)")
            print("   - GEMINI_API_KEY   -> Free at: https://aistudio.google.com/app/apikey")
            print("   - OPENROUTER_API_KEY -> Free at: https://openrouter.ai/keys\n")
            sys.exit(1)

        run_native_hud()

