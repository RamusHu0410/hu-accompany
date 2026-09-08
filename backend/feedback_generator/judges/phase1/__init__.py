"""Phase-1 judges: run on every submitted phrase, one at a time.

Each reads the same PhraseContext (that phrase's user notes already aligned
to its expected notes) and reports bar-by-bar findings plus its own 0-100
rating. Nothing here knows about other phrases -- aggregating across a whole
session is phase 2's job (summarizer.py and judges/phase2/).

JUDGES is the run order, which is also the order findings within one bar are
listed in. Add a judge by dropping a module in here and appending it.
"""

from . import articulation, dynamics, notes, pedaling, pitch, rhythm, tempo

JUDGES = (pitch, rhythm, tempo, dynamics, articulation, notes, pedaling)

__all__ = ["JUDGES", "pitch", "rhythm", "tempo", "dynamics", "articulation", "notes", "pedaling"]
