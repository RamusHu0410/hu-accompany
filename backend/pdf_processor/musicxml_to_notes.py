"""
Parse a MusicXML file into timed note events (onset + duration in
quarter-note beats).

Called from pdf_to_notes.process() -- not meant to be run standalone.
"""

import music21
from music21 import note as m21note, chord as m21chord, tempo as m21tempo, meter as m21meter

DEFAULT_BPM = 120


def convert(xml_path: str, default_bpm: float = DEFAULT_BPM) -> dict:
    score = music21.converter.parse(xml_path)

    tempos = list(score.flatten().getElementsByClass(m21tempo.MetronomeMark))
    bpm = float(tempos[0].number) if tempos else default_bpm

    ts_list = list(score.flatten().getElementsByClass(m21meter.TimeSignature))
    time_sig = f"{ts_list[0].numerator}/{ts_list[0].denominator}" if ts_list else "4/4"

    notes = []
    for part in score.parts:
        for el in part.flatten().notesAndRests:
            if isinstance(el, m21note.Rest):
                continue
            start = round(float(el.offset), 4)
            # el.quarterLength already includes augmentation dots
            # (dotted quarter = 1.5, dotted eighth = 0.75, etc.)
            duration = round(float(el.quarterLength), 4)

            if isinstance(el, m21note.Note):
                notes.append({"hz": round(el.pitch.frequency, 3), "start": start, "duration": duration})
            elif isinstance(el, m21chord.Chord):
                for p in el.pitches:
                    notes.append({"hz": round(p.frequency, 3), "start": start, "duration": duration})

    notes.sort(key=lambda n: (n["start"], n["hz"]))
    return {"bpm": bpm, "time_signature": time_sig, "notes": notes}
