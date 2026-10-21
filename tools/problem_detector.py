"""
tools/problem_detector.py
──────────────────────────
Takes a screenshot → sends to vision LLM → returns diagnosis + solution.

Usage:
    from tools.problem_detector import diagnose_screen
    result = diagnose_screen()
    print(result)
"""

import os
import base64
from tools.pc_control import take_screenshot
from core.router      import call_llm_with_vision


DIAGNOSIS_PROMPT = """
You are a technical support expert. Look at this screenshot of a user's computer screen carefully.

Your job:
1. Identify any errors, warnings, crashes, or problems visible on the screen.
2. If you see a problem, explain it in simple terms (not technical jargon).
3. Give a clear, numbered step-by-step solution to fix it.
4. If the screen looks normal (no problem), say so clearly.

Respond in the same language the user is using (check the UI language on screen).
Be concise and practical.
"""

def diagnose_screen() -> str:
    """
    Take a screenshot, analyze it with Gemini Vision, return diagnosis.
    """
    # Take screenshot
    screenshot_path = take_screenshot()

    # Read and encode as base64
    with open(screenshot_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    # Send to vision LLM
    result = call_llm_with_vision(image_data, DIAGNOSIS_PROMPT)
    return result


def diagnose_from_description(problem_text: str) -> str:
    """
    If user describes a problem in text (no screenshot needed),
    use the best LLM to diagnose and solve it.
    """
    from core.router import call_llm
    messages = [
        {
            "role": "system",
            "content": (
                "You are a Windows PC technical support expert. "
                "Diagnose the user's problem and give a clear step-by-step solution. "
                "Be practical and concise. Use numbered steps."
            )
        },
        {
            "role": "user",
            "content": f"I have this problem on my PC:\n\n{problem_text}\n\nHow do I fix it?"
        }
    ]
    from core.router import call_llm
    return call_llm(messages, task_type="diagnose_pc")
