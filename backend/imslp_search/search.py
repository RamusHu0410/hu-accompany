"""Finds candidate IMSLP works matching a free-text query."""

import re
import unicodedata

import requests

from .errors import IMSLPNetworkError
from .models import SearchHit
from .normalizer import split_title_composer

IMSLP_API_URL = "https://imslp.org/api.php"
SEARCH_LIMIT = 20
REQUEST_TIMEOUT = 10
MAX_FALLBACK_ATTEMPTS = 20

_REDIRECT_RE = re.compile(r"#REDIRECT\s*\[\[([^\]]+)\]\]", re.IGNORECASE)
_CATEGORY_REDIRECT_RE = re.compile(r"#REDIRECT\s*\[\[:?Category:([^\]]+)\]\]", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_CATEGORY_TITLE_RE = re.compile(r"^Category:(.+)$")


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


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _tokenize(text: str) -> set:
    return {
        _strip_accents(tok.strip(".,").lower())
        for tok in text.split()
        if tok.strip(".,")
    }


def find_composer_category(query: str):
    """If `query` is (entirely) a composer's name -- e.g. "Chopin" or
    "Frederic Chopin" -- return IMSLP's canonical category name for that
    composer (e.g. "Chopin, Frédéric"), resolving redirects like
    "Category:Chopin, Frederick" -> "Category:Chopin, Frédéric".

    Returns None for anything more specific than a bare composer name (e.g.
    "Chopin Nocturne Op.9 No.2"), so piece lookups aren't hijacked into a
    composer browse.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return None

    try:
        resp = requests.get(
            IMSLP_API_URL,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srnamespace": 14,
                "srlimit": 10,
                "format": "json",
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        hits = resp.json().get("query", {}).get("search", [])
    except requests.RequestException as exc:
        raise IMSLPNetworkError(f"IMSLP category search failed: {exc}") from exc

    for hit in hits:
        title = hit["title"]
        redirect = _CATEGORY_REDIRECT_RE.match(hit.get("snippet", ""))
        if redirect:
            title = f"Category:{_HTML_TAG_RE.sub('', redirect.group(1)).strip()}"

        m = _CATEGORY_TITLE_RE.match(title)
        if not m:
            continue
        composer_name = m.group(1).strip()
        name_tokens = _tokenize(composer_name.replace(",", " "))
        if name_tokens and query_tokens.issubset(name_tokens):
            return composer_name

    return None


def list_composer_works(composer_name: str, limit: int = 500) -> list:
    """List every work page (namespace 0) filed under a composer's IMSLP
    category, paginating via `cmcontinue` until exhausted or `limit` hit."""
    category_title = f"Category:{composer_name}"
    results = []
    cmcontinue = None
    pages_fetched = 0

    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category_title,
            "cmnamespace": 0,
            "cmlimit": min(limit, 500),
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue

        try:
            resp = requests.get(IMSLP_API_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise IMSLPNetworkError(f"IMSLP category listing failed: {exc}") from exc

        for member in data.get("query", {}).get("categorymembers", []):
            title = member["title"]
            name, composer = split_title_composer(title)
            results.append(
                SearchHit(
                    title=name,
                    composer=composer,
                    url=f"https://imslp.org/wiki/{title.replace(' ', '_')}",
                )
            )

        cmcontinue = data.get("continue", {}).get("cmcontinue")
        pages_fetched += 1
        if not cmcontinue or len(results) >= limit or pages_fetched >= 5:
            break

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
