"""Every setting the intake uses, in one place. The defaults are tuned for a hummed melody."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptionSettings:
    """basic_pitch.inference.predict()'s own parameters (checked against basic-pitch 0.4.0)."""

    onset_threshold: float = 0.5  # how sure an onset must be to start a note
    frame_threshold: float = 0.3  # how sure a frame must be to keep a note sounding
    minimum_note_length: float = 80.0  # milliseconds; shorter notes are dropped by basic-pitch itself
    minimum_frequency: float = 70.0  # Hz: a low hum is about 85 Hz; below this is rumble
    maximum_frequency: float = 1000.0  # Hz: a high hum is about 700 Hz; above this are harmonics
    melodia_trick: bool = True  # basic-pitch's own melody-following pass
    multiple_pitch_bends: bool = False


@dataclass(frozen=True)
class CleanupSettings:
    """How the note list is made into one clean line. Times are in milliseconds."""

    min_note_ms: float = 80.0  # a shorter note is a fragment: merged into its neighbour, or dropped
    min_stable_ms: float = 70.0  # a pitch change counts once the new pitch has held this long
    hysteresis_semitones: float = 0.2  # a new note needs this much more than half a semitone of change
    stable_spread_semitones: float = 1.0  # ...and must stay within this band while it holds (a scoop doesn't)
    bridge_gap_ms: float = 30.0  # a silence shorter than this is a glitch, not a new note
    dip_ratio: float = 0.35  # loudness falling below this share of the note's own is a re-attack
    min_dip_ms: float = 20.0
    voicing_threshold: float = 0.15  # basic-pitch's contour must reach this for a frame to have a pitch
    max_removed_share: float = 0.4  # the guardrail: cleanup may remove at most this share of the notes
    min_notes: int = 2  # ...and must leave at least this many
    max_bars: int = 16  # the arrangement step takes at most this many 4/4 bars of melody


@dataclass(frozen=True)
class AudioSettings:
    """The checks and normalizing done to the working copy of the recording."""

    silence_peak: float = 0.005  # a recording whose loudest moment is below this is silent (-46 dBFS)
    clip_level: float = 0.999
    clip_share: float = 0.001  # more samples than this at full scale: the recording clipped
    trim_top_db: float = 35.0  # trim what's this much quieter than the loudest part, at both ends
    trim_pad_ms: float = 80.0  # keep this much around the trimmed hum, so its first note isn't cut
    min_seconds: float = 0.3
    max_seconds: float = 120.0
    peak_level: float = 0.89  # normalize the loudest moment to -1 dBFS


TRANSCRIPTION = TranscriptionSettings()
CLEANUP = CleanupSettings()
AUDIO = AudioSettings()
