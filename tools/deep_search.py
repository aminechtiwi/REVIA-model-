"""
tools/deep_search.py
────────────────────
Autonomous Deep Research & Live Web Exploration Engine for REVIA.

Features:
  1. Deep Research (deep_research):
     - Iterative multi-source web crawl
     - Extracts and reads content directly from top pages
     - Synthesizes findings using the 120B cloud model into a verified, cited executive report
  2. Web Page Reader (read_web_page):
     - Fetches and parses any live URL (articles, docs, GitHub) into clean markdown
  3. Fast Web Search (fast_search):
     - Live organic search results with titles, snippets, and URLs via DuckDuckGo
"""

import sys
import os
import re
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def fast_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the live web and return a list of {title, href, body} dicts.
    Tries multiple reliable backends (api, lite, html).
    """
    for backend in ["api", "lite", "html"]:
        try:
            results = list(DDGS().text(query, backend=backend, max_results=max_results))
            if results:
                return results
        except Exception:
            continue

    print(f"[DeepSearch] All search backends returned empty for: '{query}'")
    return []


def read_web_page(url: str, max_chars: int = 4000) -> str:
    """
    Fetch a web page and convert its core readable content into clean markdown text.
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        resp.raise_for_status()

        # Parse with BeautifulSoup to remove scripts, styles, and nav junk
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
            tag.decompose()

        # Extract main text or body
        main_content = soup.find("main") or soup.find("article") or soup.find("body")
        if not main_content:
            return "Unable to parse readable content from page."

        md = markdownify(str(main_content), heading_style="ATX")
        # Collapse multiple newlines/spaces
        cleaned = re.sub(r'\n{3,}', '\n\n', md).strip()

        if len(cleaned) > max_chars:
            cleaned = cleaned[:max_chars] + "\n\n... [Content truncated for brevity] ..."

        return cleaned

    except Exception as e:
        return f"Error reading {url}: {e}"


def deep_research(topic: str, lang: str = "english") -> str:
    """
    Execute autonomous deep research on a topic:
    1. Search the web for primary sources
    2. Extract key paragraphs from top authoritative sites
    3. Synthesize findings into an in-depth, cited executive report using the 120B cloud model
    """
    from core.router import call_llm

    print(f"[REVIA DeepSearch] Starting deep research on: '{topic}'...")

    # Step 1: Initial search
    search_results = fast_search(topic, max_results=5)
    if not search_results:
        return f"Deep research could not find live web results for '{topic}'. Please verify connectivity."

    # Step 2: Read top 2-3 web pages for ground-truth facts
    gathered_context = []
    sources = []

    for i, res in enumerate(search_results[:3], 1):
        title = res.get("title", f"Source {i}")
        href = res.get("href", "")
        snippet = res.get("body", "")

        sources.append(f"- [{title}]({href})")
        gathered_context.append(f"### Source {i}: {title}\nURL: {href}\nSummary: {snippet}\n")

        # Fetch page extract
        if href and href.startswith("http"):
            page_text = read_web_page(href, max_chars=2500)
            if page_text and not page_text.startswith("Error"):
                gathered_context.append(f"Extracted Page Content:\n{page_text}\n---\n")

    compiled_evidence = "\n".join(gathered_context)

    # Step 3: Cloud Synthesis with Groq 120B
    if lang == "french":
        prompt = (
            f"Tu es un analyste de recherche expert de classe mondiale. "
            f"Voici des données réelles et récentes collectées sur le web pour le sujet : '{topic}'.\n\n"
            f"DONNÉES COLLECTÉES DU WEB :\n{compiled_evidence}\n\n"
            f"TÂCHE :\n"
            f"Synthétise un rapport de recherche approfondi, percutant et élégant en français :\n"
            f"1. **Synthèse Exécutive** : Les conclusions majeures en 2-3 phrases clés.\n"
            f"2. **Faits & Découvertes Clés** : Détails concrets, chiffres, dates et arguments prouvés.\n"
            f"3. **Perspectives & Conseils** : Recommandations ou implications pratiques.\n"
            f"4. **Sources Vérifiées** : Liste des liens sources consultés.\n"
            f"Reste factuel, rigoureux et sans verbiage inutile."
        )
    else:
        prompt = (
            f"You are a world-class executive research analyst. "
            f"Here is verified, live web data collected on the topic: '{topic}'.\n\n"
            f"COLLECTED WEB EVIDENCE:\n{compiled_evidence}\n\n"
            f"TASK:\n"
            f"Synthesize an elite, in-depth, structured research brief in English:\n"
            f"1. **Executive Summary**: The single most critical takeaways in 2-3 punchy sentences.\n"
            f"2. **Key Findings & Evidence**: Concrete discoveries, dates, technical details, and data.\n"
            f"3. **Insights & Implications**: Practical analysis or next steps.\n"
            f"4. **Verified Sources**: Bulleted markdown links to the sources examined.\n"
            f"Be precise, authoritative, and concise."
        )

    messages = [
        {"role": "system", "content": "You are REVIA Deep Research, an autonomous intelligence engine."},
        {"role": "user", "content": prompt}
    ]

    print("[REVIA DeepSearch] Synthesizing report with Cloud 120B Reasoning Engine...")
    synthesis = call_llm(messages, task_type="complex_reasoning")

    return synthesis
