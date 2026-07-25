"""Finds candidate IMSLP works matching a free-text query."""

import re

import requests

from .errors import IMSLPNetworkError
from .models import SearchHit
from .normalizer import split_title_composer

IMSLP_API_URL = "https://imslp.org/api.php"
SEARCH_LIMIT = 20
REQUEST_TIMEOUT = 10
MAX_FALLBACK_ATTEMPTS = 20

_REDIRECT_RE = re.compile(r"#REDIRECT\s*\[\[([^\]]+)\]\]", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _run_search(query: str) -> list:
    try:
        resp = requests.get(
            IMSLP_API_URL,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srnamespace": 0,
                "srlimit": SEARCH_LIMIT,
                "format": "json",
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        hits = resp.json().get("query", {}).get("search", [])
    except requests.RequestException as exc:
        raise IMSLPNetworkError(f"IMSLP search request failed: {exc}") from exc

    seen = set()
    results = []
    for hit in hits:
        title = hit["title"]
        redirect = _REDIRECT_RE.match(hit.get("snippet", ""))
        if redirect:
            title = _HTML_TAG_RE.sub("", redirect.group(1)).strip()

        if title in seen:
            continue
        seen.add(title)

        name, composer = split_title_composer(title)

        results.append(
            SearchHit(
                title=name,
                composer=composer,
                url=f"https://imslp.org/wiki/{title.replace(' ', '_')}",
            )
        )

    return results


def _plural_variants(token: str) -> list:
    if token.lower().endswith("s"):
        return [token[:-1]]
    return [token + "s"]


def _fallback_queries(tokens: list):
    """IMSLP's search index requires every query term to appear verbatim
    (no stemming), so composer + full colloquial title queries often miss
    works that are catalogued under an opus-set page (e.g. "Nocturne" vs.
    "Nocturnes") or drop a qualifier the page text never mentions (e.g. a
    trailing "No.2"). Retry with shorter prefixes of the query and with
    individual tokens' plurality flipped, most-specific first.
    """
    for length in range(len(tokens), 1, -1):
        subset = tokens[:length]
        yield " ".join(subset)
        for i, tok in enumerate(subset):
            for variant in _plural_variants(tok):
                candidate = list(subset)
                candidate[i] = variant
                yield " ".join(candidate)


def search_works(query: str) -> list:
    """Search IMSLP's full-text index and return SearchHit candidates.

    Resolves single-hop redirects (e.g. nickname pages like "Moonlight
    Sonata") using the target embedded in the search snippet, so callers
    get the canonical work title directly.
    """
    query = query.strip()
    if not query:
        return []

    hits = _run_search(query)
    if hits:
        return hits

    tokens = query.split()
    attempts = 0
    tried = {query}
    for candidate in _fallback_queries(tokens):
        if candidate in tried:
            continue
        tried.add(candidate)
        attempts += 1
        if attempts > MAX_FALLBACK_ATTEMPTS:
            break
        hits = _run_search(candidate)
        if hits:
            return hits

    return []
