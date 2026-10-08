"""The app's song settings, read as arrangement options for the band engine.

The page sends the same settings the other engines read (hum/engine/talk/settings.py): `style` names
the genre, `mood` the mood, the speed and pitch dials scale the tempo and move the key, and each
half's energy makes the verse or the chorus calmer or fuller. With no mood chosen, the emotion dial
picks one (moody or bright).
"""

from hum.engine.talk.settings import SongSettings

from .arranger import ArrangeOptions
from .presets import DEFAULT_MOOD, MOODS, preset_for


def options_from_page(page: dict | None) -> ArrangeOptions:
    """Raises ValueError when the settings aren't usable."""
    song = SongSettings.from_dict(page)
    mood = (page or {}).get("mood")
    if mood is not None and mood not in MOODS:
        raise ValueError(f"mood must be one of {', '.join(MOODS)}")
    if mood is None:
        mood = "dark" if song.emotion < 0.4 else "bright" if song.emotion > 0.6 else DEFAULT_MOOD
    return ArrangeOptions(
        preset=preset_for(song.style).id,
        mood=mood,
        speed=round(0.5 + song.speed, 3),  # as the other engines: from half to one and a half times
        transpose=round((song.pitch - 0.5) * 24),  # down or up an octave
        energy=song.energy,
    )
