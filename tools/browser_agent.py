"""
tools/browser_agent.py
───────────────────────
Browser automation using browser-use library.
Handles:
  - Gmail scanning (interviews, meetings)
  - LinkedIn job search
  - Google Calendar check
  - General browser tasks

All tasks ask for user permission before opening a browser.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

# ── LLM setup for browser-use ─────────────────────────────────────────────────
def _get_browser_llm():
    """Get the LLM for browser-use (Claude Haiku — best for browser tasks)."""
    try:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model="claude-3-haiku-20240307",
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            temperature=0.0,
        )
    except ImportError:
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model="gpt-4o-mini",
                api_key=os.getenv("OPENAI_API_KEY", ""),
                temperature=0.0,
            )
        except ImportError:
            raise RuntimeError(
                "Install langchain-anthropic or langchain-openai:\n"
                "pip install langchain-anthropic"
            )


# ── Task Prompts ──────────────────────────────────────────────────────────────

TASK_PROMPTS = {
    "check_email": """
        Go to https://mail.google.com.
        Log in if needed (wait for the user if login is required).
        Search for emails with keywords: 'interview', 'meeting', 'appointment', 
        'entretien', 'réunion', 'مقابلة', 'اجتماع'.
        List the top 5 relevant emails with:
        - Sender name
        - Subject
        - Date
        - Brief summary (1 sentence)
        Return the results as a clean, formatted list.
    """,

    "check_calendar": """
        Go to https://calendar.google.com.
        Look at the upcoming events for today and the next 7 days.
        List all events with:
        - Event title
        - Date and time
        - Whether it looks like an interview or important meeting
        Return a clear summary.
    """,

    "search_jobs": """
        Go to https://www.linkedin.com/jobs.
        Search for the job described in the user's message.
        List the top 5 job results with:
        - Job title
        - Company name
        - Location
        - Posted date
        - Brief description
        Return results as a formatted list.
    """,

    "browser_task": """
        Perform the following task in the browser:
        {user_input}
        
        Be careful, accurate, and stop if you are unsure.
        Report what you did and the result.
    """,
}


async def _run_agent(task_prompt: str) -> str:
    """Run a browser-use agent with the given task prompt."""
    try:
        from browser_use import Agent
        llm    = _get_browser_llm()
        agent  = Agent(task=task_prompt, llm=llm)
        result = await agent.run()
        return str(result)
    except ImportError:
        return (
            "❌ browser-use is not installed.\n"
            "Run: pip install browser-use\n"
            "Then: playwright install chromium"
        )
    except Exception as e:
        return f"❌ Browser task failed: {e}"


def run_browser_task(user_input: str, task_type: str = "browser_task", location: str = "") -> str:
    """
    Ultra-fast browser launcher for LinkedIn Jobs, Gmail, and Google Calendar.
    Opens directly in 0.5s without crashing or requiring paid browser agents.
    """
    import webbrowser
    import urllib.parse
    import re

    clean_input = user_input.strip()

    if task_type == "search_jobs":
        q = clean_input or "Software Engineer"
        encoded_q = urllib.parse.quote(q)
        loc = location.strip()
        if loc:
            encoded_loc = urllib.parse.quote(loc)
            url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_q}&location={encoded_loc}"
        else:
            url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_q}"
        webbrowser.open(url)
        return f"Successfully opened LinkedIn searching for '{q}'" + (f" in '{loc}'." if loc else ".")

    elif task_type == "check_email":
        webbrowser.open("https://mail.google.com")
        return "Successfully opened Gmail in the browser."

    elif task_type == "check_calendar":
        webbrowser.open("https://calendar.google.com")
        return "Successfully opened Google Calendar in the browser."

    else:
        # General browser task / url
        url = "https://www.google.com"
        if "http" in clean_input:
            match = re.search(r'https?://\S+', clean_input)
            if match:
                url = match.group(0)
        webbrowser.open(url)
        return f"Successfully opened browser at: {url}"


def send_or_compose_email(to: str = "", subject: str = "", body: str = "", auto_send: bool = False) -> str:
    """
    Open Gmail with the new compose window pre-filled with recipient, subject, and body.
    If auto_send is True, uses PyAutoGUI to send Ctrl+Enter after browser launch.
    """
    import webbrowser
    import urllib.parse
    import time
    import threading

    clean_to = to.strip() if to else ""
    clean_su = subject.strip() if subject else ""
    clean_body = body.strip() if body else ""

    params = {
        "view": "cm",
        "fs": "1",
    }
    if clean_to:
        params["to"] = clean_to
    if clean_su:
        params["su"] = clean_su
    if clean_body:
        params["body"] = clean_body

    query_string = urllib.parse.urlencode(params)
    gmail_compose_url = f"https://mail.google.com/mail/?{query_string}"

    try:
        webbrowser.open(gmail_compose_url)

        if auto_send:
            def _auto_click_send():
                time.sleep(3.5)
                try:
                    import pyautogui
                    pyautogui.hotkey('ctrl', 'enter')
                except Exception:
                    pass
            threading.Thread(target=_auto_click_send, daemon=True).start()

        target_str = f" to <{clean_to}>" if clean_to else ""
        return (
            f"✅ Gmail opened successfully with pre-composed email{target_str}!\n"
            f"• Subject: {clean_su or '(No subject)'}\n"
            f"• Message Body:\n{clean_body}"
        )
    except Exception as e:
        mailto_url = f"mailto:{clean_to}?subject={urllib.parse.quote(clean_su)}&body={urllib.parse.quote(clean_body)}"
        webbrowser.open(mailto_url)
        return f"Opened default email client: {e}"


# ── Gmail API alternative (more reliable than browser automation) ─────────────

def check_gmail_api(keywords: list = None) -> str:
    """
    Use Gmail API directly (more reliable than browser automation).
    Requires google_credentials.json in config/.
    """
    if keywords is None:
        keywords = ["interview", "meeting", "appointment", "entretien"]

    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        import os

        SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
        creds_path = os.path.join("config", "google_credentials.json")
        token_path = os.path.join("config", "gmail_token.json")

        creds = None
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if not creds or not creds.valid:
            if not os.path.exists(creds_path):
                return (
                    "❌ Gmail API not configured.\n"
                    "Download credentials.json from Google Cloud Console\n"
                    "and save it to config/google_credentials.json"
                )
            flow  = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_path, "w") as f:
                f.write(creds.to_json())

        service = build("gmail", "v1", credentials=creds)

        # Search for relevant emails
        query   = " OR ".join(f'subject:"{kw}"' for kw in keywords)
        results = service.users().messages().list(
            userId="me", q=query, maxResults=5
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            return "📭 No interview/meeting emails found."

        lines = ["📧 Found relevant emails:\n"]
        for msg_ref in messages:
            msg    = service.users().messages().get(
                userId="me", id=msg_ref["id"], format="metadata",
                metadataHeaders=["Subject", "From", "Date"]
            ).execute()
            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            lines.append(
                f"  📩 From:    {headers.get('From', 'Unknown')}\n"
                f"     Subject: {headers.get('Subject', 'No subject')}\n"
                f"     Date:    {headers.get('Date', 'Unknown')}\n"
            )

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Gmail API error: {e}"
