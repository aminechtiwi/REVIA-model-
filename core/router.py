"""
core/router.py
──────────────
REVIA Ultra-Fast Parallel Multi-Model Router v2.

Flow:
  question ⟶ cache (exact & fuzzy) ⟶ [Hit? Return instantly]
           ⟶ all models in parallel (strict 5s deadline)
           ⟶ agreement (2+ models)? ⟶ [Return immediately, skip judge]
           ⟶ otherwise: Gemini Judge scores 1-10 via fast JSON ⟶ [Return highest]
           ⟶ cache answer & return
"""

import litellm
import os
import sys
import json
import sqlite3
import hashlib
import time
import re
from concurrent.futures import ThreadPoolExecutor, wait
from difflib import SequenceMatcher
from threading import Lock
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

litellm.set_verbose = False

# ── Model Registry (Active Verified Endpoints) ───────────────────────────────
MODEL_REGISTRY = {
    # Groq (Ultra-fast LPU inference)
    "groq_120b": "groq/openai/gpt-oss-120b",
    "groq_20b": "groq/openai/gpt-oss-20b",

    # Google Gemini (Free Tier)
    "gemini_flash_lite": "gemini/gemini-flash-lite-latest",
    "gemini_flash_35": "gemini/gemini-3.5-flash",

    # OpenRouter Free Models
    "openrouter_qwen": "openrouter/qwen/qwen3.8-27b:free",
    "openrouter_reasoning": "openrouter/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
}

# Models raced in parallel for pure QA & reasoning (Ultra-fast LPU & Flash models)
PARALLEL_MODELS = [
    MODEL_REGISTRY["groq_120b"],       # 0.4s - 0.7s (120B parameters)
    MODEL_REGISTRY["groq_20b"],        # 0.3s - 0.5s
    MODEL_REGISTRY["gemini_flash_lite"], # 0.7s - 1.1s
]

# Primary and fallback judges
PRIMARY_JUDGE = MODEL_REGISTRY["gemini_flash_lite"]
FALLBACK_JUDGE = MODEL_REGISTRY["groq_120b"]

# Parallel execution timeout in seconds (tight deadline for speed)
PARALLEL_DEADLINE = 2.5

# Database path for persistent cache
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "jarvis_memory.db")
FAQ_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "knowledge_faq.json")


# ── Load Knowledge Base / FAQ ────────────────────────────────────────────────
def _load_faq_context() -> str:
    """Load system FAQ and grounding context from knowledge_faq.json."""
    if not os.path.exists(FAQ_PATH):
        return ""
    try:
        with open(FAQ_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        system_info = data.get("system", {})
        faqs = data.get("faq", [])

        lines = [
            "### OFFICIAL REVIA SYSTEM CONTEXT & FAQ (GROUND TRUTH):",
            f"Assistant: {system_info.get('name', 'REVIA')} v{system_info.get('version', '4.8')}",
            f"Environment: {system_info.get('environment', '')}",
            f"Capabilities: {system_info.get('description', '')}",
            "\nKnowledge items:"
        ]
        for item in faqs[:12]:
            lines.append(f"Q: {item.get('question', '')}")
            lines.append(f"A: {item.get('answer', '')}")

        lines.append(
            "\nSTRICT GROUNDING RULE: For any questions about REVIA, its features, capabilities, "
            "developer, or system architecture, answer ONLY from this official context. "
            "If the answer is not contained here or in your general knowledge, say honestly: 'I don't know'."
        )
        return "\n".join(lines)
    except Exception as e:
        print(f"[Router] ⚠️ Failed to load FAQ: {e}")
        return ""

GROUNDING_CONTEXT = _load_faq_context()


# ══════════════════════════════════════════════════════════════════════════════
#  PERSISTENT & IN-MEMORY FUZZY ANSWER CACHE
# ══════════════════════════════════════════════════════════════════════════════

class PersistentAnswerCache:
    """Fast in-memory cache backed by SQLite for instant repeat answers."""

    def __init__(self, max_memory_entries: int = 1000, similarity_threshold: float = 0.78):
        self._memory = {}          # norm_q -> {"answer": str, "method": str, "tokens": set}
        self._lock = Lock()
        self._threshold = similarity_threshold
        self._max_size = max_memory_entries
        self._init_db()
        self._load_from_db()

    def _init_db(self):
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS qa_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        question TEXT NOT NULL,
                        norm_q TEXT NOT NULL UNIQUE,
                        answer TEXT NOT NULL,
                        method TEXT DEFAULT 'parallel',
                        hits INTEGER DEFAULT 1,
                        created_at TEXT NOT NULL
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_norm_q ON qa_cache (norm_q)")
                conn.commit()
        except Exception as e:
            print(f"[Cache] ⚠️ Database init error: {e}")

    def _normalize(self, text: str) -> str:
        # Strip punctuation and lowercase
        cleaned = re.sub(r'[^\w\s]', '', text.lower())
        return " ".join(cleaned.split())

    def _get_tokens(self, text: str) -> set:
        stopwords = {"the", "a", "an", "is", "in", "what", "who", "how", "why", "are", "of", "to", "and", "or", "tell", "me", "please"}
        tokens = set(self._normalize(text).split())
        return tokens - stopwords

    def _load_from_db(self):
        try:
            with sqlite3.connect(DB_PATH) as conn:
                rows = conn.execute(
                    "SELECT norm_q, answer, method FROM qa_cache ORDER BY id DESC LIMIT 500"
                ).fetchall()
                for nq, ans, method in rows:
                    self._memory[nq] = {
                        "answer": ans,
                        "method": method,
                        "tokens": self._get_tokens(nq),
                    }
            if rows:
                print(f"[Cache] 📦 Loaded {len(rows)} cached answers into memory.")
        except Exception:
            pass

    def get(self, question: str) -> str | None:
        norm = self._normalize(question)
        if not norm:
            return None

        q_tokens = self._get_tokens(question)

        with self._lock:
            # 1. Exact normalized match
            if norm in self._memory:
                print(f"  [Cache] ⚡ Exact match hit! (0ms)")
                self._increment_hit(norm)
                return self._memory[norm]["answer"]

            # 2. Token overlap & SequenceMatcher fuzzy search
            best_score = 0.0
            best_match = None
            best_key = None

            for cached_norm, entry in self._memory.items():
                c_tokens = entry.get("tokens", set())
                # Jaccard token overlap
                if q_tokens and c_tokens:
                    overlap = len(q_tokens & c_tokens) / len(q_tokens | c_tokens)
                else:
                    overlap = 0.0

                str_sim = SequenceMatcher(None, norm, cached_norm).ratio()
                combined = max(overlap, str_sim)

                if combined > best_score and combined >= self._threshold:
                    best_score = combined
                    best_match = entry["answer"]
                    best_key = cached_norm

            if best_match:
                print(f"  [Cache] ⚡ Fuzzy match hit ({best_score:.0%} similarity) (0ms)")
                if best_key:
                    self._increment_hit(best_key)
                return best_match

        return None

    def put(self, question: str, answer: str, method: str = "parallel"):
        norm = self._normalize(question)
        if not norm or not answer or len(answer) < 3:
            return

        with self._lock:
            self._memory[norm] = {
                "answer": answer,
                "method": method,
                "tokens": self._get_tokens(question)
            }

        # Save asynchronously to SQLite
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("""
                    INSERT INTO qa_cache (question, norm_q, answer, method, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(norm_q) DO UPDATE SET
                        answer=excluded.answer,
                        hits=hits+1,
                        created_at=excluded.created_at
                """, (question, norm, answer, method, time.strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
        except Exception as e:
            print(f"[Cache] ⚠️ SQLite save error: {e}")

    def _increment_hit(self, norm: str):
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("UPDATE qa_cache SET hits = hits + 1 WHERE norm_q = ?", (norm,))
                conn.commit()
        except Exception:
            pass

    def clear(self):
        with self._lock:
            self._memory.clear()
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("DELETE FROM qa_cache")
                conn.commit()
        except Exception:
            pass


_answer_cache = PersistentAnswerCache()


# ══════════════════════════════════════════════════════════════════════════════
#  KEY VALIDATION & PROVIDER DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def _is_valid_key(key: str | None) -> bool:
    if not key:
        return False
    k = key.strip().lower()
    return not (k.startswith("your_") or "placeholder" in k or k == "")


# Strip placeholder dummy keys so litellm never crashes on invalid formats
for _k in ["GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ZAI_API_KEY"]:
    if not _is_valid_key(os.getenv(_k)):
        os.environ.pop(_k, None)


def _has_key_for_model(model: str) -> bool:
    if model.startswith("gemini/"):
        return bool(os.getenv("GEMINI_API_KEY"))
    if model.startswith("openrouter/"):
        return bool(os.getenv("OPENROUTER_API_KEY"))
    if model.startswith("groq/"):
        return bool(os.getenv("GROQ_API_KEY"))
    if model.startswith("anthropic/") or model.startswith("claude-"):
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    if model.startswith("gpt-"):
        return bool(os.getenv("OPENAI_API_KEY"))
    return False


def get_available_models() -> list[str]:
    return [m for m in PARALLEL_MODELS if _has_key_for_model(m)]


# ── Roles Chain for Backward Compatibility ────────────────────────────────────
ROLES_CHAIN = {
    "master": [
        MODEL_REGISTRY["groq_120b"],
        MODEL_REGISTRY["gemini_flash_lite"],
        MODEL_REGISTRY["groq_20b"],
    ],
    "reasoning": [
        MODEL_REGISTRY["openrouter_reasoning"],
        MODEL_REGISTRY["groq_120b"],
        MODEL_REGISTRY["gemini_flash_lite"],
    ],
    "coding": [
        MODEL_REGISTRY["groq_120b"],
        MODEL_REGISTRY["openrouter_qwen"],
        MODEL_REGISTRY["gemini_flash_lite"],
    ],
    "multilingual": [
        MODEL_REGISTRY["openrouter_qwen"],
        MODEL_REGISTRY["groq_120b"],
        MODEL_REGISTRY["gemini_flash_lite"],
    ],
    "fast": [
        MODEL_REGISTRY["groq_20b"],
        MODEL_REGISTRY["gemini_flash_lite"],
    ],
    "vision": [
        MODEL_REGISTRY["gemini_flash_lite"],
        MODEL_REGISTRY["gemini_flash_35"],
    ],
}


def get_available_models_for_role(role: str) -> list[str]:
    candidates = ROLES_CHAIN.get(role, ROLES_CHAIN["master"])
    avail = [m for m in candidates if _has_key_for_model(m)]
    if not avail:
        avail = [m for m in PARALLEL_MODELS if _has_key_for_model(m)]
    return avail


def get_model_for_task(task_type: str) -> str:
    models = get_available_models_for_role("master")
    return models[0] if models else MODEL_REGISTRY["groq_120b"]


def classify_task(user_input: str) -> str:
    return "default"


# ══════════════════════════════════════════════════════════════════════════════
#  PARALLEL MODEL RACING ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def _call_model_worker(model: str, messages: list, timeout: float = 5.0) -> tuple[str, str | None]:
    """Single model call executed in thread pool."""
    try:
        t0 = time.time()
        resp = litellm.completion(
            model=model,
            messages=messages,
            temperature=0.6,
            max_tokens=1500,
            timeout=timeout,
        )
        elapsed = round(time.time() - t0, 2)
        content = resp.choices[0].message.content
        if content:
            content = content.strip()
            print(f"  [Parallel] ✅ {model.split('/')[-1]} answered in {elapsed}s ({len(content)} chars)")
            return (model, content)
        return (model, None)
    except Exception as e:
        print(f"  [Parallel] ⚠️ {model.split('/')[-1]} skipped: {str(e)[:50]}")
        return (model, None)


def _check_agreement(candidates: dict[str, str]) -> str | None:
    """
    Check if 2 or more models gave substantially the same answer.
    If so, return the most complete one immediately, skipping the judge!
    """
    items = list(candidates.items())
    if len(items) < 2:
        return None

    for i in range(len(items)):
        agreeing = [items[i]]
        m1, a1 = items[i]
        a1_norm = " ".join(a1.lower().split()[:80])

        for j in range(i + 1, len(items)):
            m2, a2 = items[j]
            a2_norm = " ".join(a2.lower().split()[:80])

            len_ratio = len(a1) / max(len(a2), 1)
            if 0.35 < len_ratio < 2.8:
                sim = SequenceMatcher(None, a1_norm, a2_norm).ratio()
                if sim >= 0.68:
                    agreeing.append((m2, a2))

        if len(agreeing) >= 2:
            # Pick the most complete among agreeing models
            winner = max(agreeing, key=lambda x: len(x[1]))
            models_str = " + ".join([m.split('/')[-1] for m, _ in agreeing])
            print(f"  [Agreement] 🤝 High consensus between [{models_str}] → Skipping judge!")
            return winner[1]

    return None


def _judge_candidates(question: str, candidates: dict[str, str]) -> str:
    """
    Ask Gemini (or Groq 120B fallback) to score each candidate 1-10 via fast JSON.
    Returns the answer with the highest score.
    """
    entries = []
    models = list(candidates.keys())
    for idx, (m, ans) in enumerate(candidates.items(), 1):
        trunc = ans[:1200] if len(ans) > 1200 else ans
        entries.append(f"--- CANDIDATE {idx} (from {m.split('/')[-1]}) ---\n{trunc}")

    candidates_block = "\n\n".join(entries)

    judge_prompt = (
        "You are an expert answer judge. The user asked:\n"
        f"\"{question}\"\n\n"
        "Evaluate the following AI answers based on accuracy, completeness, helpfulness, and language:\n\n"
        f"{candidates_block}\n\n"
        "Score each candidate from 1 to 10.\n"
        "Return ONLY valid JSON format with no additional commentary:\n"
        '{"scores": [{"candidate": 1, "score": 9}, {"candidate": 2, "score": 7}]}'
    )

    judge_models = [PRIMARY_JUDGE, FALLBACK_JUDGE]
    for jm in judge_models:
        if not _has_key_for_model(jm):
            continue
        try:
            t0 = time.time()
            resp = litellm.completion(
                model=jm,
                messages=[{"role": "user", "content": judge_prompt}],
                temperature=0.0,
                max_tokens=200,
                timeout=4.0,
            )
            raw = resp.choices[0].message.content.strip()
            elapsed = round(time.time() - t0, 2)

            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            data = json.loads(raw)
            scores = data.get("scores", [])
            if scores:
                best = max(scores, key=lambda s: s.get("score", 0))
                best_idx = best.get("candidate", 1) - 1
                if 0 <= best_idx < len(models):
                    winner_model = models[best_idx]
                    print(f"  [Judge] ⚖️ Evaluated by {jm.split('/')[-1]} in {elapsed}s → Winner: {winner_model.split('/')[-1]} (Score: {best.get('score')}/10)")
                    return candidates[winner_model]
        except Exception as e:
            print(f"  [Judge] ⚠️ {jm.split('/')[-1]} scoring failed: {e}")
            continue

    # Fallback if judge JSON parsing fails: pick the longest answer
    print("  [Judge] Fallback: selecting most comprehensive candidate.")
    return max(candidates.values(), key=len)


def parallel_smart_route(messages: list) -> str:
    """
    Main Parallel Multi-Model Pipeline:
      1. Check Cache (exact & fuzzy)
      2. Call all models in parallel with strict 5s deadline
      3. Check Agreement between models (skip judge if consensus found)
      4. If divergent, Judge scores 1-10 via fast JSON
      5. Cache and return
    """
    # Extract user question
    user_question = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_question = msg.get("content", "")
            break

    if not user_question:
        return "No input provided."

    # ── 1. Cache Check ────────────────────────────────────────────────────────
    cached_answer = _answer_cache.get(user_question)
    if cached_answer:
        return cached_answer

    # ── 2. Determine Available Models ─────────────────────────────────────────
    available = get_available_models()
    if not available:
        return "No AI models available. Please verify API keys in .env."

    print(f"\n[Router] ⚡ Racing {len(available)} models in parallel (Deadline: {PARALLEL_DEADLINE}s)...")

    # Inject Context / Grounding FAQ
    augmented_messages = list(messages)
    if GROUNDING_CONTEXT:
        if augmented_messages and augmented_messages[0]["role"] == "system":
            augmented_messages[0] = {
                "role": "system",
                "content": augmented_messages[0]["content"] + "\n\n" + GROUNDING_CONTEXT
            }
        else:
            augmented_messages.insert(0, {"role": "system", "content": GROUNDING_CONTEXT})

    # ── 3. Call all models in parallel with strict deadline ────────────────────
    candidates = {}
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=len(available)) as executor:
        futures = {
            executor.submit(_call_model_worker, model, augmented_messages, timeout=PARALLEL_DEADLINE): model
            for model in available
        }

        pending = set(futures.keys())

        while pending:
            time_spent = time.time() - start_time
            if time_spent >= PARALLEL_DEADLINE:
                print(f"  [Router] ⏰ 5s deadline reached — proceeding with {len(candidates)} responses.")
                for f in pending:
                    f.cancel()
                break

            remaining_time = max(0.1, PARALLEL_DEADLINE - time_spent)
            # Check for completed futures every 250ms
            done, pending = wait(pending, timeout=min(0.25, remaining_time))

            for future in done:
                model_name, answer = future.result()
                if answer:
                    candidates[model_name] = answer

            # Early consensus check: if 2+ models arrived and agree, exit immediately!
            if len(candidates) >= 2:
                agreed = _check_agreement(candidates)
                if agreed:
                    for f in pending:
                        f.cancel()
                    _answer_cache.put(user_question, agreed, method="agreement")
                    return agreed

                # If fast models have already replied (>=2 responses and >=1.0s), proceed directly to judge!
                if len(candidates) >= len(available) or (len(candidates) >= 2 and time_spent >= 1.0):
                    for f in pending:
                        f.cancel()
                    break

    if not candidates:
        return "All models timed out or failed to respond. Please try again."

    total_time = round(time.time() - start_time, 2)
    print(f"  [Router] 📊 Collected {len(candidates)} responses in {total_time}s.")

    # ── 4. Single candidate ───────────────────────────────────────────────────
    if len(candidates) == 1:
        chosen = list(candidates.values())[0]
        _answer_cache.put(user_question, chosen, method="single")
        return chosen

    # ── 5. Judge divergent candidates ─────────────────────────────────────────
    best_answer = _judge_candidates(user_question, candidates)
    _answer_cache.put(user_question, best_answer, method="judge")
    return best_answer


# ══════════════════════════════════════════════════════════════════════════════
#  MASTER & WORKER CALLS (Preserved for agent tool loops)
# ══════════════════════════════════════════════════════════════════════════════

def call_master(messages: list, tools: list = None, temperature: float = 0.5, timeout: int = 15):
    """Invokes Master AI with native tool calling."""
    models_to_try = get_available_models_for_role("master")
    if not models_to_try:
        err = "❌ No active model configured."
        if tools:
            class _Dummy:
                content = err
                tool_calls = None
            return _Dummy()
        return err

    last_err = None
    for model_name in models_to_try:
        try:
            kwargs = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 1200,
                "timeout": timeout,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            resp = litellm.completion(**kwargs)
            msg = resp.choices[0].message
            return msg if tools else (msg.content or "")
        except Exception as e:
            print(f"[Master] {model_name} failed: {e}")
            last_err = e
            continue

    fail_msg = f"Master call failed: {last_err}"
    if tools:
        class _Fail:
            content = fail_msg
            tool_calls = None
        return _Fail()
    return fail_msg


def call_worker(role: str, messages: list, temperature: float = 0.6, timeout: int = 10) -> str:
    """Invokes specialized worker."""
    models_to_try = get_available_models_for_role(role)
    for model_name in models_to_try:
        try:
            resp = litellm.completion(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=1500,
                timeout=timeout,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            continue
    return "Worker execution failed."


def call_llm(messages: list, task_type: str = "default", temperature: float = 0.7, tools: list = None):
    """
    Main LLM entry point:
      - Tool-calling agent loops -> call_master
      - General conversation & reasoning -> parallel_smart_route (5s deadline, agreement, judge, cache)
    """
    if tools or task_type in ("agent_loop", "browser_task"):
        return call_master(messages, tools=tools, temperature=temperature)

    return parallel_smart_route(messages)


# ── Vision Model Invocation ───────────────────────────────────────────────────
def call_llm_with_vision(image_base64: str, prompt: str) -> str:
    """Calls vision model for screen diagnostics."""
    vision_models = get_available_models_for_role("vision")
    if not vision_models:
        return "❌ Vision analysis failed: No vision model configured."

    for m in vision_models:
        try:
            resp = litellm.completion(
                model=m,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"}
                        }
                    ]
                }],
                max_tokens=2048,
                timeout=20,
            )
            return resp.choices[0].message.content or "No response from vision model."
        except Exception as e:
            print(f"[Vision] {m} failed: {e}")
            continue

    return "❌ Vision analysis failed."


def clear_answer_cache():
    """Clear both memory and database answer cache."""
    _answer_cache.clear()
    print("[Router] 🗑️ Answer cache cleared.")
