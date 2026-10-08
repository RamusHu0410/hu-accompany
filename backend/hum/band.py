"""The band engine (hum/song) as the views use it: where its files live, and the song's notes for
the app's graph. Kept out of the views so they stay thin and import nothing circular."""

from pathlib import Path

from hum import paths
from hum.song import Mix, Project, arrange, mix, options_from_page
from hum.song.render import swung
from hum.transcription import Transcription, transcription_for


def transcription(hum: Path) -> Transcription:
    return transcription_for(hum, paths.data_dir() / "transcriptions")


def project_for(hum: Path, page_settings: dict | None) -> Project:
    """The hum arranged with the page's settings. Raises ValueError for unusable settings and
    PipelineError when the hum has no tune."""
    options = options_from_page(page_settings)  # before the slow part: bad settings fail fast
    return arrange(transcription(hum), options, hum=hum.name)


def render(project: Project) -> Mix:
    return mix(project, paths.data_dir() / "stems")


def notes_for_graph(hum: Path, project: Project) -> dict:
    """What the app's graph draws: the notes sung (exactly as hummed) and the tune as the song's
    melody plays it the first time through, both in seconds from their first note."""
    heard = transcription(hum)
    verse = project.section("verse")
    melody = next((t for t in project.tracks if t.role == "melody"), None)
    first_time = [n for n in (melody.notes if melody else []) if n.start >= verse.start][: len(project.phrase)]
    origin = swung(first_time[0].start, project.swing) if first_time else 0.0
    spb = project.seconds_per_beat
    return {
        "sung": [{"midi": n.pitch, "start": n.start, "duration": n.duration} for n in heard.raw],
        "played": [
            {
                "midi": n.pitch,
                "start": round((swung(n.start, project.swing) - origin) * spb, 3),
                "duration": round((swung(n.end, project.swing) - swung(n.start, project.swing)) * spb, 3),
            }
            for n in first_time
        ],
    }
