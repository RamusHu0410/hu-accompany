"""The song project in a few lines, for Gemini: enough to understand "the drums", "the chorus",
"faster" and "louder" against what the song is now, small enough to send with every message."""

from hum.song.harmony import Chord
from hum.song.instruments import instrument_name
from hum.song.presets import MOODS, PRESETS
from hum.song.project import ROLES, Project

INTENSITY = {0: "sparse", 1: "light", 2: "full"}


def summarize(project: Project) -> str:
    preset, mood = PRESETS.get(project.preset), MOODS.get(project.mood)
    lines = [
        f"Genre: {preset.label if preset else project.preset}. Mood: {mood.label if mood else project.mood}.",
        f"Tempo: {round(project.tempo)} bpm. Key: {project.tonic} {project.mode}"
        + (f" ({project.transpose:+d} semitones from the hum)." if project.transpose else " (as hummed)."),
        "Sections: " + ", ".join(f"{s.name} {s.bars} bars {INTENSITY[s.intensity]}" for s in project.sections) + ".",
    ]
    verse = next((s for s in project.sections if s.name == "verse"), None)
    if verse:
        bars = [c for c in project.chords if verse.start_bar <= c.bar < verse.start_bar + verse.bars]
        lines.append("Verse chords: " + " | ".join(Chord(c.root, c.quality, c.degree).name() for c in bars) + ".")
    lines.append("Parts:")
    soloed = any(t.solo for t in project.tracks)
    for track in project.tracks:
        state = ["muted"] if track.mute else []
        if track.solo:
            state.append("soloed")
        elif soloed:
            state.append("silent while another part is soloed")
        fx = track.effects
        details = f"volume {round(track.volume * 100)}%, reverb {round(fx.reverb * 100)}%"
        lines.append(f"- {track.role}: {instrument_name(track.program, track.is_drums)}, {details}"
                     + (f", {', '.join(state)}" if state else ""))
    missing = [r for r in ROLES if not any(t.role == r for t in project.tracks)]
    if missing:
        lines.append("Not in the song (can be added): " + ", ".join(missing) + ".")
    return "\n".join(lines)
