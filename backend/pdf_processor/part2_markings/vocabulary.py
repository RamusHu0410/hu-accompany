"""
Closed-vocabulary classifier for OCR'd text tokens found on a score page.

Ported from an earlier prototype's `phase4_markings.py`. Classification is
closed-vocabulary (an exact word/symbol lookup), not free text recognition:
pytesseract run over a whole music page inevitably misreads noteheads/beams/
slurs as stray characters, and open-ended text interpretation would treat
that noise as content. Matching only against the specific tempo/dynamic/
expression/technique vocabulary the terms actually come from means garbage
tokens essentially never accidentally collide with a real marking word.

Unlike that prototype, bare digits (which could be a tuplet number, a
fingering, or a rehearsal mark) are not classified at all -- disambiguating
them needs page/note context this module doesn't have, and an unclassified
digit is at least as likely to be OCR noise.
"""

import difflib
import re

TEMPO_WORDS = {
    "larghissimo": 24, "grave": 35, "largo": 45, "lento": 50, "larghetto": 55,
    "adagio": 65, "adagietto": 70, "andante": 88, "andantino": 92,
    "moderato": 108, "allegretto": 112, "allegro": 132, "vivace": 160,
    "vivo": 160, "presto": 184, "prestissimo": 200,
}

DYNAMIC_WORDS = {
    "ppp": 0.05, "pp": 0.15, "p": 0.25, "mp": 0.40, "mf": 0.60,
    "f": 0.75, "ff": 0.88, "fff": 0.95, "fp": 0.60, "sf": 0.85, "sfz": 0.85,
}

EXPRESSION_WORDS = {
    "dolce", "cantabile", "espressivo", "sempre", "rit.", "rit", "ritenuto",
    "accel.", "accel", "accelerando", "a tempo", "atempo", "legato",
    "staccato", "cresc.", "cresc", "crescendo", "dim.", "dim", "diminuendo",
    "poco", "molto", "meno", "piu", "più", "subito", "scherzando", "mosso",
    "moto", "primo", "agitato", "marcato", "tranquillo", "grazioso",
    "leggiero",
}

TECHNIQUE_WORDS = {
    "ped.": "pedal_down", "ped": "pedal_down", "una corda": "una_corda",
    "tre corde": "tre_corde", "sim.": "simile", "simile": "simile",
}

_TIME_SIG_RE = re.compile(r"^([2-9]|1[0-9])\s*/\s*([2-9]|1[0-9])$")

# Minimum length before a word is even considered for fuzzy matching.
# Dynamics/short abbreviations are excluded entirely -- a 1-3 character
# token is close (by edit distance) to dozens of unrelated short strings,
# so fuzzy-matching those would turn essentially any stray OCR noise into a
# marking. Longer words don't have that problem: something else would have
# to misread as within 1-2 edits of "scherzando" or "crescendo", which
# essentially never happens by coincidence from misread notation ink.
_FUZZY_MIN_LEN = 5
_FUZZY_CUTOFF = 0.8


def _fuzzy_lookup(word: str, vocabulary) -> "str | None":
    if len(word) < _FUZZY_MIN_LEN:
        return None
    match = difflib.get_close_matches(word, vocabulary, n=1, cutoff=_FUZZY_CUTOFF)
    return match[0] if match else None


def classify_token(text: str) -> "tuple[str, object] | None":
    """
    Returns (marking_type, value) if `text` matches the closed vocabulary,
    else None. Checked in order of specificity so e.g. "p" (dynamic) isn't
    shadowed by a longer expression match.
    """
    stripped = text.strip()
    # Tempo/expression words are often printed parenthesized, e.g.
    # "(Moto primo)" -- tesseract tokenizes per printed word, so the
    # brackets end up stuck to the first/last word of the phrase.
    lower = stripped.strip("()[]").lower().rstrip(".,;:")

    m = _TIME_SIG_RE.match(stripped)
    if m:
        return "time_signature", f"{m.group(1)}/{m.group(2)}"

    if lower in DYNAMIC_WORDS:
        return "dynamic", DYNAMIC_WORDS[lower]

    if lower in TEMPO_WORDS:
        return "tempo", TEMPO_WORDS[lower]

    if lower in TECHNIQUE_WORDS:
        return "technique", TECHNIQUE_WORDS[lower]

    if lower in EXPRESSION_WORDS:
        return "expression", lower

    # OCR misreads a correctly-segmented word's individual letters far more
    # often than it spells an entirely different vocabulary word by
    # coincidence (e.g. "Crese." for "cresc.", "leggtero" for "leggiero"),
    # so a fuzzy fallback is safe here where it would not be for the exact
    # lookups above.
    match = _fuzzy_lookup(lower, TEMPO_WORDS)
    if match:
        return "tempo", TEMPO_WORDS[match]

    match = _fuzzy_lookup(lower, TECHNIQUE_WORDS)
    if match:
        return "technique", TECHNIQUE_WORDS[match]

    match = _fuzzy_lookup(lower, EXPRESSION_WORDS)
    if match:
        return "expression", match

    return None
