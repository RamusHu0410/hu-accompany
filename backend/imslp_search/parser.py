"""Fetches an IMSLP work page and parses its raw wikitext into sections.

IMSLP work pages are built from a big "imslppage" template whose body is
split into ALL-CAPS, asterisk-fenced markers (*****FILES*****, *****WORK
INFO*****, ...). Within *****FILES*****, MediaWiki headings nest as:

    ===Arrangements and Transcriptions===   (level 3, optional)
    ====Complete====                        (level 4, movement/scope)
    =====For Violin and Piano (Hofmann)=====  (level 5, instrumentation)

Each heading's own file entries -- {{#fte:imslpfile ...}} templates -- sit
directly beneath it, before the next heading of any level. A level appearing
without a fully-nested child (e.g. a level-4 "Complete" heading straight
under the top of the file with no level-5 child) *is* itself a version: it
holds the file entries for the work's original scoring.
"""

import html
import re

import requests

from .errors import IMSLPNetworkError
from .models import Edition, RawSection

IMSLP_API_URL = "https://imslp.org/api.php"
REQUEST_TIMEOUT = 15

_MARKER_RE = re.compile(r"\*{3,}\s*([A-Z /]+?)\s*\*{3,}")
_HEADER_RE = re.compile(r"^(={3,5})\s*(.*?)\s*\1\s*$", re.MULTILINE)
_FIELD_RE = re.compile(r"\n\|\s*([^=\n]+?)[ \t]*=[ \t]*(.*?)(?=\n\|[^=\n]+=|\Z)", re.DOTALL)
_FILE_BLOCK_RE = re.compile(r'<div id="IMSLP(\d+)"')
_FILE_TITLE_RE = re.compile(r'title="(?:File:)?([^"]+?\.\w{2,4})"')
_FILE_TITLE_WINDOW = 1500


def page_title_from_url(url: str) -> str:
    """Extract the MediaWiki page title from an https://imslp.org/wiki/... url."""
    title = url.rsplit("/wiki/", 1)[-1]
    return title.replace("_", " ")


def fetch_work_page(page_title: str) -> tuple:
    """Fetch a work page's wikitext (for section/edition structure) and its
    rendered HTML (for the numeric per-file IMSLP ids the wikitext doesn't
    carry) in a single API call. Returns (wikitext, html)."""
    try:
        resp = requests.get(
            IMSLP_API_URL,
            params={
                "action": "parse",
                "page": page_title,
                "format": "json",
                "prop": "wikitext|text",
            },
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise IMSLPNetworkError(f"IMSLP page fetch failed: {exc}") from exc

    if "error" in data:
        raise IMSLPNetworkError(f"IMSLP page fetch failed: {data['error']}")

    parse = data["parse"]
    return parse["wikitext"]["*"], parse["text"]["*"]


def normalize_filename(name: str) -> str:
    """Canonicalize a filename for cross-referencing the wikitext's
    underscore-separated "File Name" fields against the rendered HTML's
    space-separated, HTML-entity-escaped file titles."""
    return html.unescape(name).replace("_", " ").strip().lower()


def parse_file_ids(page_html: str) -> dict:
    """Map normalized filename -> numeric IMSLP file id, read from each
    file row's `<div id="IMSLPxxxxx">` block in the rendered HTML. This is
    the only place a file's real download id (used to build
    https://imslp.org/wiki/Special:ImagefromIndex/{id}) is exposed --
    it's absent from the wikitext."""
    file_ids = {}
    for m in _FILE_BLOCK_RE.finditer(page_html):
        window = page_html[m.end() : m.end() + _FILE_TITLE_WINDOW]
        title_match = _FILE_TITLE_RE.search(window)
        if not title_match:
            continue
        key = normalize_filename(title_match.group(1))
        file_ids.setdefault(key, m.group(1))
    return file_ids


def _find_section(wikitext: str, marker_name: str) -> str:
    """Return the text between *****MARKER_NAME***** and the next marker."""
    markers = list(_MARKER_RE.finditer(wikitext))
    for i, m in enumerate(markers):
        if m.group(1).strip() == marker_name:
            start = m.end()
            end = markers[i + 1].start() if i + 1 < len(markers) else len(wikitext)
            return wikitext[start:end]
    return ""


def _find_matching_close(text: str, open_start: int) -> int:
    """Given the index of a '{{' opener, return the index just past its
    matching '}}', accounting for nested templates."""
    depth = 0
    i = open_start
    n = len(text)
    while i < n - 1:
        if text[i : i + 2] == "{{":
            depth += 1
            i += 2
            continue
        if text[i : i + 2] == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return i
            continue
        i += 1
    return -1


def _extract_templates(text: str, template_name: str) -> list:
    marker = "{{#fte:" + template_name
    blocks = []
    idx = 0
    while True:
        start = text.find(marker, idx)
        if start == -1:
            break
        end = _find_matching_close(text, start)
        if end == -1:
            break
        blocks.append(text[start:end])
        idx = end
    return blocks


def _parse_fields(block: str, template_name: str) -> dict:
    prefix = "{{#fte:" + template_name
    inner = block[len(prefix) : -2]
    fields = {}
    for m in _FIELD_RE.finditer(inner):
        fields[m.group(1).strip()] = m.group(2).strip()
    return fields


def _edition_from_fields(fields: dict) -> Edition:
    file_names = [
        v
        for k, v in fields.items()
        if k.startswith("File Name") and v
    ]
    return Edition(
        editor=fields.get("Editor") or None,
        publisher=fields.get("Publisher Information") or None,
        copyright=fields.get("Copyright") or None,
        scanner=fields.get("Scanner") or None,
        date_submitted=fields.get("Date Submitted") or None,
        misc_notes=fields.get("Misc. Notes") or None,
        file_description=fields.get("File Description 1") or fields.get("File Description") or None,
        file_names=file_names,
    )


def parse_work_info(wikitext: str) -> dict:
    section = _find_section(wikitext, "WORK INFO")
    info = {}
    for m in _FIELD_RE.finditer(section):
        info[m.group(1).strip()] = m.group(2).strip()
    return info


def parse_sections(wikitext: str) -> list:
    """Parse the *****FILES***** block into a flat list of RawSection."""
    section_text = _find_section(wikitext, "FILES")
    if not section_text:
        return []

    headers = [
        (len(m.group(1)), m.group(2).strip().lstrip("*").strip(), m.start(), m.end())
        for m in _HEADER_RE.finditer(section_text)
    ]

    sections = []
    category = "score"
    movement = None
    instrumentation = None

    # Files can appear before any heading at all -- e.g. simple works with
    # a single edition and no Arrangements/instrumentation subdivision.
    # Without this, such works parse to zero sections/choices even though
    # their files are sitting right there in the text.
    leading_end = headers[0][2] if headers else len(section_text)
    leading_content = section_text[:leading_end]
    leading_blocks = _extract_templates(leading_content, "imslpfile")
    if leading_blocks:
        editions = [_edition_from_fields(_parse_fields(b, "imslpfile")) for b in leading_blocks]
        sections.append(
            RawSection(
                category=category,
                movement=movement,
                instrumentation_label=instrumentation,
                editions=editions,
            )
        )

    for i, (level, title, _hstart, hend) in enumerate(headers):
        content_end = headers[i + 1][2] if i + 1 < len(headers) else len(section_text)
        content = section_text[hend:content_end]

        if level == 3:
            category = "arrangement" if "arrangement" in title.lower() else "score"
            movement = None
            instrumentation = None
        elif level == 4:
            movement = title
            instrumentation = None
        else:  # level == 5
            instrumentation = title

        file_blocks = _extract_templates(content, "imslpfile")
        if not file_blocks:
            continue

        editions = [_edition_from_fields(_parse_fields(b, "imslpfile")) for b in file_blocks]
        sections.append(
            RawSection(
                category=category,
                movement=movement,
                instrumentation_label=instrumentation,
                editions=editions,
            )
        )

    return sections
