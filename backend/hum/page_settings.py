"""The app's song settings, translated into the epic engine's terms.

The app sends the same settings talk mode edits (hum/engine/talk/settings.py): three dials, a list of
instruments and an energy for each half. The epic engine wants them as ArrangeSettings.
"""

import hashlib

from hum.engine.audio.arrange import ArrangeSettings, ExtraPart
from hum.engine.audio.arrange.ensembles import ensemble_for_word
from hum.engine.talk.settings import DRUMS, SongSettings
from hum.engine.talk.song import BACKGROUND_VOLUME, LOW, OTHER_NAMES, PROGRAMS

UNSET_STYLE = "cinematic"  # when the app hasn't picked a style: the orchestra at its fullest
LEAD_VOLUME = {"soft": 80, "loud": 127}  # "normal" keeps the style's own balance
# The app's starting instrument list is one lead, "synth pad" (the backend's own default: "synth").
# That's no choice yet, so the ensemble picks the lead; any other list is the listener's.
UNCHOSEN_LEADS = {"synth pad", "synth"}


def variation_for(recording: str) -> int:
    """Each recording gets its own combination of instruments, and keeps it: changing its song's
    settings doesn't swap the band. `recording` is the unique name the upload was saved under (so
    even the same hum recorded twice gets a new combination)."""
    return int(hashlib.sha256(recording.encode()).hexdigest()[:12], 16)


def settings_from_page(page: dict | None, variation: int | None = None) -> tuple[str, ArrangeSettings]:
    """The app's song settings in the arrangement's terms. `variation` picks who plays
    (ensembles.py) unless the style word names an ensemble ("rock", "electronic"...).
    Raises ValueError when they aren't usable."""
    song = SongSettings.from_dict(page)
    page_lead = next((part for part in song.instruments if part.role == "lead"), None)
    lead = page_lead
    if lead is not None and len(song.instruments) == 1 and lead.name in UNCHOSEN_LEADS and lead.level == "normal":
        lead = None  # the app's starting list: nothing chosen yet
    parts = []
    for part in song.instruments:
        if part is page_lead:
            continue
        name = OTHER_NAMES.get(part.name, part.name)
        if name == DRUMS:
            parts.append(ExtraPart(0, "drums", BACKGROUND_VOLUME[part.level], part.section))
        elif name in PROGRAMS:
            parts.append(ExtraPart(PROGRAMS[name], "bass" if name in LOW else "chords", BACKGROUND_VOLUME[part.level], part.section))
    lead_name = OTHER_NAMES.get(lead.name, lead.name) if lead else None
    return song.style or UNSET_STYLE, ArrangeSettings(
        tempo_scale=round(0.5 + song.speed, 3),  # the same as talk mode: from half to one and a half times
        transpose=round((song.pitch - 0.5) * 24),  # down or up to an octave
        mode="minor" if song.emotion < 0.4 else "major" if song.emotion > 0.6 else None,
        lead=PROGRAMS.get(lead_name) if lead_name and lead_name != DRUMS else None,
        lead_volume=LEAD_VOLUME.get(lead.level) if lead else None,
        parts=tuple(parts),
        energy=song.energy,
        ensemble=ensemble_for_word(song.style),
        variation=variation,
    )
