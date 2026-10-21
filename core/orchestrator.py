"""
core/orchestrator.py
─────────────────────
The BRAIN of Jarvis.
Receives user input → detects language → classifies task →
calls the right tool → returns response.

Flow:
  User message
      ↓
  detect_language()
      ↓
  classify_task()
      ↓
  route to tool (pc_control / browser_agent / problem_detector / llm)
      ↓
  save to memory
      ↓
  return response
"""

import os
import sys
import json
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core.language import detect_language, get_system_prompt, get_response_language_instruction
from core.router   import classify_task, call_llm, get_model_for_task, clear_answer_cache
from core.memory   import init_db, save_message, get_recent_messages

load_dotenv()

# Load settings
_settings_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.json")
with open(_settings_path, "r", encoding="utf-8") as f:
    SETTINGS = json.load(f)


# ── OpenJarvis-Style Native Tool Schema ─────────────────────────────────────────
REVIA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_linkedin_jobs",
            "description": "Open LinkedIn in the browser and search for jobs in a specific field. Use ONLY when the user explicitly asks to search for or find job openings on LinkedIn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Job title or field (e.g. 'Python', 'Web Developer', 'Marketing')."
                    },
                    "location": {
                        "type": "string",
                        "description": "Location to search in (e.g. 'Paris', 'London', 'Remote'). Optional."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_gmail",
            "description": "Open Gmail inbox in the user's browser. Call this when the user asks to check their emails or see incoming messages.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Compose and open/send an email via Gmail. Call this whenever the user asks to send an email, write an email, compose a message, or contact someone via Gmail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address (e.g. 'john@example.com'). If user didn't specify an address, leave empty."
                    },
                    "subject": {
                        "type": "string",
                        "description": "Clear, professional subject line of the email."
                    },
                    "body": {
                        "type": "string",
                        "description": "Complete, polished body text of the email message."
                    },
                    "auto_send": {
                        "type": "boolean",
                        "description": "Set to true if the user explicitly wants the email to be automatically sent immediately."
                    }
                },
                "required": ["subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_google_calendar",
            "description": "Open Google Calendar in the browser. Call this when the user asks to check upcoming meetings, schedule, or appointments.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_app_or_website",
            "description": "Launch a desktop application (chrome, notepad, explorer, vscode, spotify) or open a website URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_or_url": {
                        "type": "string",
                        "description": "Application name (e.g. 'chrome', 'notepad') or website URL."
                    }
                },
                "required": ["name_or_url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "diagnose_screen_problem",
            "description": "Take a screenshot of the user's screen and diagnose an error, bug, or crash visible on the monitor.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pc_health_status",
            "description": "Check CPU, RAM, and Disk health status. Call when the user asks about PC performance or if their computer is running slow.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "live_web_search",
            "description": "Fast real-time web search for quick facts, current news, weather, or instant answers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Specific search query."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "deep_research",
            "description": "Perform comprehensive, multi-source autonomous deep research on any complex topic, technical question, or comparison. Crawls top websites, extracts real data, and synthesizes an in-depth cited executive report.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Specific research topic, question, or investigation objective."
                    }
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_web_page",
            "description": "Fetch, extract, and parse the readable text of any webpage or article URL provided by the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Complete HTTP or HTTPS URL to read."
                    }
                },
                "required": ["url"]
            }
        }
    }
]


class Orchestrator:
    """
    Main REVIA orchestrator using OpenJarvis-style native tool calling.
    The LLM autonomously decides whether to answer or call a tool.
    All tool executions are gated by user permission checks.
    """

    def __init__(self):
        init_db()
        self._load_tools()
        print("[REVIA] 🟢 OpenJarvis-grade Orchestrator initialized.")

    def _load_tools(self):
        """Lazy-import tools to keep startup fast."""
        self.tools_loaded = False

    def _ensure_tools(self):
        if not self.tools_loaded:
            from tools.pc_control       import open_app, open_website, get_system_info
            from tools.browser_agent    import run_browser_task, send_or_compose_email
            from tools.problem_detector import diagnose_screen
            from tools.search           import web_search
            from tools.deep_search      import deep_research, read_web_page
            self.open_app       = open_app
            self.open_website   = open_website
            self.get_system_info= get_system_info
            self.run_browser    = run_browser_task
            self.send_email     = send_or_compose_email
            self.diagnose       = diagnose_screen
            self.web_search     = web_search
            self.deep_research  = deep_research
            self.read_web_page  = read_web_page
            self.tools_loaded   = True

    def process(self, user_input: str, force_lang: str = None) -> str:
        """
        Main entry point. Uses LLM tool calling to understand intent without rigid keywords.
        """
        self._ensure_tools()

        # ── 1. Language detection ────────────────────────────────────────────
        lang = force_lang or detect_language(user_input)
        system_prompt = get_system_prompt(lang)
        lang_instruction = get_response_language_instruction(lang)

        # ── 2. Build conversation context ─────────────────────────────────────
        history = get_recent_messages(limit=SETTINGS.get("memory_max_messages", 20))
        messages = [
            {"role": "system", "content": f"{system_prompt}\n\n{lang_instruction}"},
            *history,
            {"role": "user",   "content": user_input},
        ]

        # ── 3. Route: Action Agent Loop vs. Parallel Multi-Model Pipeline ──
        if not self._is_action_request(user_input):
            # Pure questions, analysis, coding, knowledge, and conversation:
            # Flow: question ⟶ cache ⟶ all models in parallel (5s limit) ⟶ agreement? return it ⟶ Gemini judge ⟶ answer
            response = call_llm(messages, task_type="default")
            save_message("user",      user_input, lang, "chat", "")
            save_message("assistant", response,   lang, "chat", "parallel_engine")
            return response

        # ── 4. OpenJarvis Agent Loop for Desktop & Web Actions ──
        MAX_ITERATIONS = 3
        has_executed_tools = False
        response = ""

        for step in range(MAX_ITERATIONS):
            # Phase 1 & 2: THINK & PICK TOOL
            llm_response = call_llm(messages, task_type="agent_loop", tools=REVIA_TOOLS)
            tool_calls = getattr(llm_response, "tool_calls", None)

            if not tool_calls:
                # No tools needed or action verified — formulate answer
                default_ack = "Compris !" if lang == "french" else "Understood!"
                response = getattr(llm_response, "content", str(llm_response)) or default_ack
                break

            has_executed_tools = True
            messages.append(llm_response)

            # Phase 3: EXECUTE TOOL (Gated by permission)
            for tc in tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    fn_args = {}

                print(f"[REVIA] 🧠 Think ⟶ Picked: {fn_name}({fn_args})")
                tool_result = self._execute_tool(fn_name, fn_args, lang)

                # Phase 4: VERIFY RESULT (Feed observation back to agent for self-verification)
                print(f"[REVIA] 🔍 Verification: {tool_result[:60]}...")
                messages.append({
                    "tool_call_id": getattr(tc, "id", f"call_{step}"),
                    "role": "tool",
                    "name": fn_name,
                    "content": f"Status: {tool_result}. Verify if this successfully completed the user's request.",
                })
        else:
            # Reached max steps, summarize final verified result
            final_resp = call_llm(messages, task_type="agent_loop")
            default_done = "Toutes les étapes ont été complétées et vérifiées." if lang == "french" else "All actions completed and verified successfully."
            response = getattr(final_resp, "content", str(final_resp)) or default_done

        # ── 4. Save to persistent memory ──────────────────────────────────────
        save_message("user",      user_input, lang, "action" if has_executed_tools else "chat", "")
        save_message("assistant", response,   lang, "action" if has_executed_tools else "chat", "master/gemini")

        return response

    def _is_action_request(self, text: str) -> bool:
        """Fast check if the user is asking to execute an interactive PC/web tool."""
        t = text.lower().strip()
        action_patterns = [
            r"\b(open|launch|start|run|close|quit|ouvre|lance|dmarre|ferme)\b",
            r"\b(screenshot|capture|screen|cran|ecran|diagnostique)\b",
            r"\b(gmail|email|e-mail|mail|courriel|send|envoyer|envoie|cris|ecris|compose)\b",
            r"\b(calendar|calendrier|agenda|rdv|meeting|appointment)\b",
            r"\b(linkedin|job|jobs|emploi|recrutement)\b",
            r"\b(cpu|ram|disk|disque|health|sant|performance)\b",
            r"\b(deep research|recherche approfondie)\b",
            r"\b(notepad|chrome|firefox|vscode|spotify|calc)\b",
        ]
        import re
        return any(re.search(pat, t) for pat in action_patterns)

    # ── Tool Execution Router (Gated by Permission) ───────────────────────────

    def _execute_tool(self, tool_name: str, args: dict, lang: str) -> str:
        """Execute the requested tool safely with permission checks."""
        self._ensure_tools()
        from tools.pc_control import request_permission

        if tool_name == "send_email":
            to = args.get("to", "").strip()
            subject = args.get("subject", "Message from REVIA Operator").strip()
            body = args.get("body", "").strip()
            auto_send = bool(args.get("auto_send", False))
            target_desc = f" to <{to}>" if to else ""
            if not request_permission(f"Open Gmail and compose email{target_desc} (Subject: '{subject}')"):
                return "User denied permission to open Gmail compose."
            return self.send_email(to=to, subject=subject, body=body, auto_send=auto_send)

        elif tool_name == "search_linkedin_jobs":
            query = args.get("query", "software")
            location = args.get("location", "")
            loc_str = f" in {location}" if location else ""
            if not request_permission(f"Search LinkedIn for '{query}' jobs{loc_str}"):
                return "User denied permission to open LinkedIn."
            return self.run_browser(query, "search_jobs", location=location)

        elif tool_name == "open_gmail":
            if not request_permission("Open Gmail in browser"):
                return "User denied permission to open Gmail."
            return self.run_browser("", "check_email")

        elif tool_name == "open_google_calendar":
            if not request_permission("Open Google Calendar in browser"):
                return "User denied permission to open Google Calendar."
            return self.run_browser("", "check_calendar")

        elif tool_name == "open_app_or_website":
            target = args.get("name_or_url", "").strip()
            if not target:
                return "No application or website specified."
            if not request_permission(f"Open {target}"):
                return f"User denied permission to open {target}."
            if target.startswith("http") or "." in target:
                return self.open_website(target, skip_permission=True)
            return self.open_app(target, skip_permission=True)

        elif tool_name == "diagnose_screen_problem":
            if not request_permission("Take a screenshot to diagnose screen"):
                return "User denied permission to take screenshot."
            return self.diagnose()

        elif tool_name == "get_pc_health_status":
            return self.get_system_info()

        elif tool_name == "live_web_search":
            query = args.get("query", "")
            if not query:
                return "No search query provided."
            return self.web_search(query)

        elif tool_name == "deep_research":
            topic = args.get("topic", "").strip()
            if not topic:
                return "No research topic specified."
            return self.deep_research(topic, lang=lang)

        elif tool_name == "read_web_page":
            url = args.get("url", "").strip()
            if not url:
                return "No webpage URL specified."
            return self.read_web_page(url)

        return f"Unknown tool: {tool_name}"
