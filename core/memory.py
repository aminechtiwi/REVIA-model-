"""
core/memory.py
──────────────
Conversation memory using SQLite (built into Python — no install needed).
Stores and retrieves the last N messages for context.
Also tracks usage stats per model.
"""

import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "jarvis_memory.db")


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    with _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                language    TEXT DEFAULT 'english',
                task_type   TEXT DEFAULT 'default',
                model_used  TEXT DEFAULT '',
                created_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_stats (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                model       TEXT NOT NULL,
                task_type   TEXT,
                tokens_in   INTEGER DEFAULT 0,
                tokens_out  INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL
            )
        """)
        conn.commit()


def save_message(role: str, content: str, language: str = "english",
                 task_type: str = "default", model_used: str = ""):
    """Save a message (user or assistant) to memory."""
    with _get_connection() as conn:
        conn.execute(
            """INSERT INTO messages (role, content, language, task_type, model_used, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (role, content, language, task_type, model_used, datetime.now().isoformat())
        )
        conn.commit()


def get_recent_messages(limit: int = 20) -> list:
    """
    Get the last N messages formatted for LLM context.
    Returns list of {"role": ..., "content": ...} dicts.
    """
    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    # Reverse so oldest is first (correct order for LLM)
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def clear_memory():
    """Wipe conversation history and answer cache (start fresh)."""
    with _get_connection() as conn:
        conn.execute("DELETE FROM messages")
        try:
            conn.execute("DELETE FROM qa_cache")
        except Exception:
            pass
        conn.commit()
    try:
        from core.router import clear_answer_cache
        clear_answer_cache()
    except Exception:
        pass


def log_usage(model: str, task_type: str, tokens_in: int = 0, tokens_out: int = 0):
    """Track how many tokens each model used."""
    with _get_connection() as conn:
        conn.execute(
            """INSERT INTO usage_stats (model, task_type, tokens_in, tokens_out, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (model, task_type, tokens_in, tokens_out, datetime.now().isoformat())
        )
        conn.commit()


def get_usage_summary() -> str:
    """Return a readable summary of API usage."""
    with _get_connection() as conn:
        rows = conn.execute(
            """SELECT model, SUM(tokens_in) as tin, SUM(tokens_out) as tout, COUNT(*) as calls
               FROM usage_stats GROUP BY model ORDER BY calls DESC"""
        ).fetchall()
    if not rows:
        return "No usage recorded yet."
    lines = ["📊 API Usage Summary:", "─" * 40]
    for r in rows:
        lines.append(f"  {r['model']}: {r['calls']} calls | {r['tin']} in / {r['tout']} out tokens")
    return "\n".join(lines)
