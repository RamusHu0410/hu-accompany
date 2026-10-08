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
        # stripTies() merges a note tied to its neighbour(s) into a single
        # note whose duration is the sum of the tied pieces. Without this,
        # a note held across a barline (or any tie) comes back as two or
        # more separate notesAndRests entries, so playback re-articulates
        # what should be one sustained sound -- e.g. a whole note tied to a
        # quarter becomes a whole note *and* a quarter struck again a beat
        # later, instead of a single 5-beat note. matchByPitch also folds
        # away chord ties correctly (each pitch merged independently).
        try:
            flat = part.stripTies(matchByPitch=True).flatten()
        except Exception:
            # stripTies can choke on malformed OMR output (overlapping
            # voices, ties with no partner); fall back to the raw stream so
            # a bad page still yields notes rather than nothing.
            flat = part.flatten()

        for el in flat.notesAndRests:
            if isinstance(el, m21note.Rest):
                continue
            # Grace notes come through with quarterLength 0.0 at the same
            # offset as the main note they ornament. oemer doesn't reliably
            # detect grace notes anyway, and a zero-duration event sitting
            # on top of a real note is an unplayable duplicate on the
            # timeline, so drop anything without positive duration.
            if float(el.quarterLength) <= 0 or el.duration.isGrace:
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
    for i, n in enumerate(notes):
        n["id"] = i
    return {"bpm": bpm, "time_signature": time_sig, "notes": notes}
