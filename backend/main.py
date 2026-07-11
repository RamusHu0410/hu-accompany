import os
import re
import requests
"""from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def chat(prompt: str) -> str:
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
    )
    return response.text
"""

# ─────────────────────────────────────────────────────────────────────────────
# IMSLP score lookup
# ─────────────────────────────────────────────────────────────────────────────

IMSLP_SEARCH_API_URL = "https://imslp.org/api.php"
IMSLP_SEARCH_LIMIT   = 20

_REDIRECT_RE = re.compile(r"#REDIRECT\s*\[\[([^\]]+)\]\]", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_COMPOSER_RE = re.compile(r"\(([^()]+)\)\s*$")


def search_imslp(query: str) -> list:
    """
    Search IMSLP via its MediaWiki full-text search API, returning
    [{"name", "composer", "url"}, ...].

    A single request against the wiki's search index, rather than paging
    through IMSLP's full work catalog — this also matches nicknames (e.g.
    "Moonlight Sonata"), since those exist on IMSLP as redirect pages to the
    canonical work title; we resolve single-hop redirects using the target
    embedded in the search snippet.
    """
    query = query.strip()
    if not query:
        return []

    resp = requests.get(IMSLP_SEARCH_API_URL, params={
        "action":      "query",
        "list":        "search",
        "srsearch":    query,
        "srnamespace": 0,
        "srlimit":     IMSLP_SEARCH_LIMIT,
        "format":      "json",
    }, timeout=10)
    resp.raise_for_status()
    hits = resp.json().get("query", {}).get("search", [])

    seen    = set()
    results = []
    for hit in hits:
        title = hit["title"]
        redirect = _REDIRECT_RE.match(hit.get("snippet", ""))
        if redirect:
            title = _HTML_TAG_RE.sub("", redirect.group(1)).strip()

        if title in seen:
            continue
        seen.add(title)

        composer_match = _COMPOSER_RE.search(title)
        composer = composer_match.group(1) if composer_match else ""
        name     = title[:composer_match.start()].strip() if composer_match else title

        results.append({
            "name":     name,
            "composer": composer,
            "url":      f"https://imslp.org/wiki/{title.replace(' ', '_')}",
        })

    return results


