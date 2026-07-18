"""Turns raw, wiki-markup-flavored scrape data into clean, display-ready values."""

import re

from .models import Choice, Edition

_COMPOSER_SUFFIX_RE = re.compile(r"\s*\([^()]+\)\s*$")
_COMPOSER_RE = re.compile(r"\(([^()]+)\)\s*$")
_FOR_RE = re.compile(r"^\*?\s*For\s+(.*?)\s*(?:\(([^)]+)\))?\s*$", re.IGNORECASE)
_AND_RE = re.compile(r"\band\b", re.IGNORECASE)

_LINKED_EDITOR_RE = re.compile(r"\{\{LinkEd\|([^|}]*)\|([^|}]*)(?:\|[^}]*)?\}\}")
_WIKILINK_RE = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")
_TAG_RE = re.compile(r"<[^>]+>")


def normalize_title(raw_title: str) -> str:
    """Strip the "(Composer, Name)" suffix IMSLP appends to page titles and
    tidy up underscores/whitespace."""
    if not raw_title:
        return ""
    title = raw_title.replace("_", " ").strip()
    title = _COMPOSER_SUFFIX_RE.sub("", title)
    return re.sub(r"\s+", " ", title).strip()


def split_title_composer(raw_title: str):
    """Split an IMSLP page title of the form "Work Name (Composer, First)"
    into (work_name, composer)."""
    title = (raw_title or "").replace("_", " ").strip()
    m = _COMPOSER_RE.search(title)
    if not m:
        return title, ""
    return title[: m.start()].strip(), m.group(1).strip()


def normalize_instrument(label):
    """Parse an IMSLP section heading like "For Violin and Piano (Hofmann)"
    into (["Violin", "Piano"], "Hofmann")."""
    if not label:
        return [], None
    m = _FOR_RE.match(label)
    if not m:
        return [label.strip()], None
    instruments_part, arranger = m.group(1), m.group(2)
    instruments_part = _AND_RE.sub(",", instruments_part)
    instruments = [p.strip() for p in instruments_part.split(",") if p.strip()]
    return instruments, (arranger.strip() if arranger else None)


def detect_arrangement(category: str) -> bool:
    return category == "arrangement"


def extract_editor(raw):
    """Strip IMSLP wiki markup (LinkEd templates, wikilinks, <br> separators)
    down to a plain, human-readable editor name/list."""
    if not raw:
        return None
    text = _LINKED_EDITOR_RE.sub(lambda m: f"{m.group(1)} {m.group(2)}".strip(), raw)
    text = _WIKILINK_RE.sub(lambda m: m.group(1), text)
    text = _BR_RE.sub(", ", text)
    text = _TEMPLATE_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    text = re.sub(r"\s*,\s*,+", ", ", text)
    text = text.strip(" ,")
    if not text or re.fullmatch(r"\([^()]*\)", text):
        # A bare "(German)"-style leftover with no name means the source
        # field only carried a template marker (e.g. {{FE}} for "first
        # edition"), not a named editor.
        return None
    return text


def build_choice(section, index: int, work_url: str, default_instrument: str) -> Choice:
    """Normalize a parser.RawSection into an API-ready Choice."""
    is_arrangement = detect_arrangement(section.category)
    primary_edition = section.editions[0] if section.editions else Edition()
    editor = extract_editor(primary_edition.editor)

    if section.instrumentation_label:
        instruments, arranger = normalize_instrument(section.instrumentation_label)
    else:
        instruments = [default_instrument] if default_instrument else []
        arranger = None

    titled = [i.title() for i in instruments]
    instrumentation = " + ".join(titled) if titled else (default_instrument or "Unknown").title()

    if is_arrangement:
        name = f"{' and '.join(titled)} Arrangement" if titled else "Arrangement"
    else:
        name = f"{instrumentation} Solo" if len(titled) == 1 else instrumentation

    movement = section.movement
    if movement and movement.strip().lower() == "complete":
        movement = None

    return Choice(
        id=str(index),
        name=name,
        instrumentation=instrumentation,
        type="Arrangement" if is_arrangement else "Original Score",
        imslp_url=work_url,
        movement=movement,
        arranger=arranger,
        editor=editor,
    )
