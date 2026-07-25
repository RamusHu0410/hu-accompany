"""Orchestrates the IMSLP metadata lookup: search -> parse -> normalize,
with a database cache in front so repeat lookups skip IMSLP entirely.
"""

from api.models import Version, Work
from imslp import normalizer, parser
from imslp import search as imslp_search
from imslp.errors import WorkNotFoundError

DEFAULT_INSTRUMENT = "Unknown"


def _work_to_dict(work: Work) -> dict:
    return {
        "title": work.title,
        "composer": work.composer,
        "imslp_url": work.imslp_url,
        "choices": [
            {
                "id": str(v.id),
                "name": v.name,
                "instrumentation": v.instrumentation,
                "type": v.type,
                "imslp_url": v.imslp_url,
                "movement": v.movement,
                "arranger": v.arranger,
                "editor": v.editor,
                "file_name": v.file_name,
            }
            for v in work.versions.all()
        ],
    }


def _fetch_and_cache(title: str, composer: str, url: str) -> Work:
    wikitext, page_html = parser.fetch_work_page(parser.page_title_from_url(url))
    work_info = parser.parse_work_info(wikitext)
    default_instrument = work_info.get("Instrumentation") or DEFAULT_INSTRUMENT
    file_id_map = parser.parse_file_ids(page_html)

    sections = parser.parse_sections(wikitext)
    choices = [
        normalizer.build_choice(section, i, url, default_instrument, file_id_map)
        for i, section in enumerate(sections)
    ]

    work = Work.objects.create(
        title=normalizer.normalize_title(title) or title,
        composer=composer,
        imslp_url=url,
    )
    Version.objects.bulk_create(
        [
            Version(
                work=work,
                name=c.name,
                instrumentation=c.instrumentation,
                type=c.type,
                movement=c.movement,
                arranger=c.arranger,
                editor=c.editor,
                imslp_url=c.imslp_url,
                file_name=c.file_name,
            )
            for c in choices
        ]
    )
    return work


def search(query: str = "", url: str = None) -> dict:
    """Look up a work's available versions/arrangements/editions.

    If `url` is given (e.g. the caller already disambiguated via
    /api/search), it's used directly and no IMSLP search call is made.
    Otherwise the top IMSLP search hit for `query` is used, matching the
    "piece name in, versions list out" contract for a first pass.
    """
    if url:
        cached = Work.objects.filter(imslp_url=url).first()
        if cached:
            return _work_to_dict(cached)

        page_title = parser.page_title_from_url(url)
        title, composer = normalizer.split_title_composer(page_title)
        work = _fetch_and_cache(title, composer, url)
        return _work_to_dict(work)

    hits = imslp_search.search_works(query)
    if not hits:
        raise WorkNotFoundError(f"No IMSLP results for {query!r}")
    best = hits[0]

    cached = Work.objects.filter(imslp_url=best.url).first()
    if cached:
        return _work_to_dict(cached)

    work = _fetch_and_cache(best.title, best.composer, best.url)
    return _work_to_dict(work)
