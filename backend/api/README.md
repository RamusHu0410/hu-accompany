# API Routes

Defined in `backend/server/urls.py` (root, includes `api.urls`) and
`backend/api/urls.py` (all actual routes). Every route is POST-only and
CSRF-exempt; request/response bodies are JSON.

| Method | Path | View |
|---|---|---|
| POST | `/developer/chat/` | `api.views.chat_view` |
| POST | `/developer/api/search` | `api.views.search_view` |
| POST | `/api/imslp/search` | `api.views.imslp_search_view` |
| POST | `/api/imslp/download` | `imslp_downloader.api.download_view` |
| POST | `/api/score/process` | `api.views.process_score_view` |
| POST | `/api/score/process-omr` | `api.views.process_score_omr_view` |

---

## POST `/developer/chat/`
Dev/debug echo endpoint.

**Body:** `{"prompt": "..."}`
**Response:** `{"response": "<prompt echoed back>"}`
**Errors:** 400 if `prompt` missing/blank or body isn't valid JSON.

## POST `/developer/api/search`
Dev/debug IMSLP search (thin wrapper, superseded by `/api/imslp/search`).

**Body:** `{"query": "..."}`
**Response:** `{"query": "...", "results": [...]}`
**Errors:** 400 if `query` missing/blank or invalid JSON.

## POST `/api/imslp/search`
Look up a work's available versions/editions on IMSLP (cached in the DB
after the first lookup). A bare composer name returns that composer's
full work list; anything more specific resolves to the top search hit.

**Body:** `{"query": "...", "url": "<optional IMSLP work URL>"}`
(`url` skips the IMSLP search call and looks up that exact page directly.)
**Response:** `{"title", "composer", "imslp_url", "choices": [{"id", "name", "instrumentation", "type", "imslp_url", "movement", "arranger", "editor", "file_name"}, ...]}`
**Errors:** 400 invalid JSON / missing query+url, 404 work not found, 502 IMSLP network error.

## POST `/api/imslp/download`
Download a specific score version/edition from IMSLP into permanent
storage (drives a real browser through IMSLP's disclaimer/subscribe
flow). Returns the existing file immediately if already downloaded.

**Body:** `{"score_id": "...", "imslp_url": "..."}`
**Response:** `{"status": "completed"|"failed", "score_id": "...", "file_path": "storage/scores/<Composer>/<Work>/<file>.pdf", "error": "..."}`
`file_path` is the canonical identifier passed to the two `/api/score/*` endpoints below.
**Errors:** 400 missing score_id / invalid IMSLP URL, 502 browser/download failure, 503 IMSLP subscription-gated, 500 file save failure.

## POST `/api/score/process`
Convert a stored score PDF into a notes JSON using `backend/processor`
(a hand-built, non-ML OMR heuristic), optionally with a debug PDF
showing every detected note circled and pitch-labeled on the original
score.

**Body:** `{"file_path": "storage/scores/...", "bpm": 120, "debug_pdf": true}`
**Response:** `{"file_path", "json_path", "note_count", "debug_pdf_path"?}`
**Errors:** 400 missing file_path / invalid JSON, 404 file not found, 500 processing error.

## POST `/api/score/process-omr`
Convert a stored score PDF into notes JSON using `backend/pdf_processor`
(the oemer ML-based OMR pipeline): splits the PDF into per-page PNGs,
runs OMR to MusicXML with a debug PNG per page (every detected
notehead/clef/barline/etc. boxed and labeled), then parses timed note
events. All output files are written next to the source PDF in storage.

**Body:** `{"file_path": "storage/scores/..."}`
**Response:**
```json
{
  "file_path": "storage/scores/...",
  "pages": ["storage/scores/.../page-001.png", ...],
  "musicxml": ["storage/scores/.../page-001.musicxml", ...],
  "debug_png": ["storage/scores/.../page-001_debug.png", ...],
  "notes_json": ["storage/scores/.../page-001_notes.json", ...],
  "bpm": 120,
  "time_signature": "4/4",
  "note_count": 296,
  "timing": {"split": 0.13, "omr": 199.56, "notes": 0.09, "total": 199.78}
}
```
**Errors:** 400 missing file_path / invalid JSON, 404 file not found, 500 processing error.

Note: this and `/api/score/process` are two independent OMR pipelines
(ML-based vs. heuristic-based) kept side by side in the codebase — see
`backend/pdf_processor/README.md` and `backend/processor/processor.py`.
