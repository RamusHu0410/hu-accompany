import os
import requests

# ─────────────────────────────────────────────────────────────────────────────
# IMSLP score lookup
# ─────────────────────────────────────────────────────────────────────────────

IMSLP_API_URL      = "https://imslp.org/imslpscripts/API.ISCR.php"
IMSLP_PAGE_SIZE     = 1000
IMSLP_MAX_REQUESTS  = 40   # safety cap on round-trips per search


def _imslp_fetch_page(start: int) -> dict:
    # IMSLP's API takes its params as a single slash-separated string rather
    # than a normal "&"-joined query string.
    url = (f"{IMSLP_API_URL}?account=worklist/disclaimer=accepted"
           f"/sort=id/type=2/start={start}/retformat=json")
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _imslp_entries(page: dict) -> list:
    keys = sorted((k for k in page if k != "metadata"), key=int)
    return [page[k] for k in keys]


def search_imslp(title: str) -> list:
    """
    Search IMSLP's public work catalog for scores whose title starts with
    `title` (case-insensitive), returning [{"name", "composer", "url"}, ...].

    IMSLP's API has no text-search parameter: "account=worklist" only pages
    through the full catalog (hundreds of thousands of entries), sorted
    alphabetically by title (sort=id). We exploit that ordering to binary
    search for the matching page(s) instead of scanning linearly.
    """
    query = title.strip().lower()
    if not query:
        return []

    requests_made = 0

    def fetch(start: int) -> dict:
        nonlocal requests_made
        requests_made += 1
        if requests_made > IMSLP_MAX_REQUESTS:
            raise RuntimeError("IMSLP search exceeded its request budget")
        return _imslp_fetch_page(start)

    def page_first_id(page: dict) -> str:
        entries = _imslp_entries(page)
        return entries[0]["id"].lower() if entries else "￿"

    # Exponential search to bracket the page range containing `query`.
    lo_page, hi_page = 0, 1
    hi_data = fetch(hi_page * IMSLP_PAGE_SIZE)
    while hi_data["metadata"]["moreresultsavailable"] and page_first_id(hi_data) < query:
        lo_page = hi_page
        hi_page *= 2
        hi_data = fetch(hi_page * IMSLP_PAGE_SIZE)

    # Binary search within [lo_page, hi_page] for the smallest page whose
    # first entry is alphabetically >= query.
    while lo_page < hi_page:
        mid = (lo_page + hi_page) // 2
        if page_first_id(fetch(mid * IMSLP_PAGE_SIZE)) < query:
            lo_page = mid + 1
        else:
            hi_page = mid

    # The page located above is the first whose *first* entry is >= query,
    # but matches can start partway through the previous page — back up one.
    start = max(0, lo_page - 1) * IMSLP_PAGE_SIZE

    # Scan forward, collecting matches, until titles no longer start with
    # `query` (guaranteed contiguous by the alphabetical sort) or the
    # catalog ends.
    matches = []
    while True:
        page = fetch(start)
        entries = _imslp_entries(page)
        stop = False
        for entry in entries:
            key = entry["id"].lower()
            if key.startswith(query):
                iv = entry.get("intvals", {})
                matches.append({
                    "name":     iv.get("worktitle", entry["id"]),
                    "composer": iv.get("composer", ""),
                    "url":      entry.get("permlink", ""),
                })
            elif key > query:
                stop = True
                break
        if stop or not page["metadata"]["moreresultsavailable"]:
            break
        start += IMSLP_PAGE_SIZE

    return matches
