"""Phase-2 judges: run once per session, over every phase-1 phrase at once.

Each reads a PieceContext (piece metadata, every stored phase-1 file, the
aggregated scores, every finding) and contributes one Phase2/<Name>.json
file. This is for judgements that only exist at whole-piece scale -- style
period today -- not for restating phase 1.

The whole-piece summary itself is not a judge: it lives in
feedback_generator/summarizer.py and is written alongside these.
"""

from . import era

JUDGES = (era,)

__all__ = ["JUDGES", "era"]
