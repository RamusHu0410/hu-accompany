"""Orchestrates the IMSLP metadata lookup: search -> parse -> normalize,
with a database cache in front so repeat lookups skip IMSLP entirely.
"""

from api.models import Version, Work
from imslp_search import normalizer, parser
from imslp_search import search as imslp_search_module
from imslp_search.errors import WorkNotFoundError

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


def browse_composer(composer_name: str) -> dict:
    """List every work filed under a composer's IMSLP category.

    Used when the query names a composer only (e.g. "Chopin"), where
    resolving to a single top search hit would arbitrarily pick one piece
    instead of showing everything the composer has available.
    """
    works = imslp_search_module.list_composer_works(composer_name)
    if not works:
        raise WorkNotFoundError(f"No works found for composer {composer_name!r}")
    return {
        "composer": composer_name,
        "works": [{"title": w.title, "composer": w.composer, "url": w.url} for w in works],
    }


def search(query: str = "", url: str = None) -> dict:
    """Look up a work's available versions/arrangements/editions, or -- if
    the query names a composer only -- every work by that composer.

    If `url` is given (e.g. the caller already disambiguated via
    /api/search), it's used directly and no IMSLP search call is made.
    Otherwise, a bare composer name (e.g. "Chopin") returns that composer's
    full work list (see `browse_composer`); anything more specific resolves
    to the top IMSLP search hit for `query`, matching the "piece name in,
    versions list out" contract for a first pass.
    """
    if url:
        cached = Work.objects.filter(imslp_url=url).first()
        if cached:
            return _work_to_dict(cached)

        page_title = parser.page_title_from_url(url)
        title, composer = normalizer.split_title_composer(page_title)
        work = _fetch_and_cache(title, composer, url)
        return _work_to_dict(work)

    composer_name = imslp_search_module.find_composer_category(query)
    if composer_name:
        return browse_composer(composer_name)

    hits = imslp_search_module.search_works(query)
    if not hits:
        raise WorkNotFoundError(f"No IMSLP results for {query!r}")
    best = hits[0]

    cached = Work.objects.filter(imslp_url=best.url).first()
    if cached:
        return _work_to_dict(cached)

    work = _fetch_and_cache(best.title, best.composer, best.url)
    return _work_to_dict(work)
