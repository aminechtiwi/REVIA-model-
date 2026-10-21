"""
tools/search.py
────────────────
Web search tool. Uses SerpAPI if key is available,
falls back to DuckDuckGo (free, no key needed).
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")


def web_search(query: str, num_results: int = 5) -> str:
    """
    Search the web and return a formatted string of results.
    Uses SerpAPI if available, otherwise DuckDuckGo.
    """
    if SERPAPI_KEY:
        return _serpapi_search(query, num_results)
    else:
        return _duckduckgo_search(query, num_results)


def _serpapi_search(query: str, num_results: int = 5) -> str:
    """Search using SerpAPI (100 free/month)."""
    try:
        params = {
            "api_key": SERPAPI_KEY,
            "engine":  "google",
            "q":       query,
            "num":     num_results,
        }
        response = requests.get("https://serpapi.com/search", params=params, timeout=10)
        data     = response.json()

        results = data.get("organic_results", [])
        if not results:
            return "No results found."

        lines = [f"🔍 Search results for: {query}\n"]
        for i, r in enumerate(results[:num_results], 1):
            title   = r.get("title", "No title")
            snippet = r.get("snippet", "")
            link    = r.get("link", "")
            lines.append(f"{i}. {title}\n   {snippet}\n   🔗 {link}\n")

        return "\n".join(lines)

    except Exception as e:
        return f"Search failed: {e}"


def _duckduckgo_search(query: str, num_results: int = 5) -> str:
    """
    Free DuckDuckGo live search via DDGS. Returns organic search results.
    """
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        for backend in ["api", "lite", "html"]:
            try:
                results = list(DDGS().text(query, backend=backend, max_results=num_results))
                if results:
                    break
            except Exception:
                continue
        else:
            return "No web results found."

        lines = [f"🔍 Web Search Results for: '{query}':\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "No Title")
            snippet = r.get("body", "")
            link = r.get("href", "")
            lines.append(f"{i}. **{title}**\n   {snippet}\n   🔗 {link}\n")

        return "\n".join(lines)
    except Exception as err:
        return f"Web search encountered an error: {err}"
