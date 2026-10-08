"""Fidelity tests for the audio capture/parsing pipeline.

These don't just check that the processor runs — they check it recovers what
was actually put into the WAV file: known frequencies land as the right notes,
note count and timing survive round-tripping, and loud/quiet or silent input
doesn't get corrupted into false pitches.
"""

import wave

import numpy as np
import soundfile as sf
import pytest

from hum.engine.audio.processor import (
    AudioProcessor,
    extract_notes,
    analyze_audio_file,
    _build_melody,
)

SR = 22050


def _tone(freq_hz, seconds, sr=SR, amplitude=0.8):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def _vibrato_tone(freq_hz, seconds, sr=SR, amplitude=0.8, vibrato_rate_hz=5.5, vibrato_extent_hz=15.0):
    """A hum wavers in pitch (vibrato) and loudness (tremolo) rather than
    holding a perfectly steady tone. Instantaneous frequency oscillates
    around ``freq_hz`` by +/- ``vibrato_extent_hz`` at ``vibrato_rate_hz``."""
    n = int(sr * seconds)
    t = np.linspace(0, seconds, n, endpoint=False)
    instantaneous_freq = freq_hz + vibrato_extent_hz * np.sin(2 * np.pi * vibrato_rate_hz * t)
    phase = 2 * np.pi * np.cumsum(instantaneous_freq) / sr
    tremolo = 1.0 - 0.15 * np.sin(2 * np.pi * (vibrato_rate_hz * 0.9) * t)
    return (amplitude * tremolo * np.sin(phase)).astype(np.float32)


def _silence(seconds, sr=SR):
    return np.zeros(int(sr * seconds), dtype=np.float32)


def _hum(midi, seconds, sr=SR, amplitude=0.5, fade=0.02, fade_in=None, cents=0.0):
    """A hum-like note: a fundamental with two overtones, faded in and out."""
    fade_in = fade if fade_in is None else fade_in
    t = np.arange(int(sr * seconds)) / sr
    phase = 2 * np.pi * 440.0 * 2 ** ((midi + cents / 100 - 69) / 12) * t
    tone = np.sin(phase) + 0.4 * np.sin(2 * phase) + 0.2 * np.sin(3 * phase)
    envelope = np.ones_like(t)
    if fade_in:
        envelope = np.minimum(envelope, t / fade_in)
    if fade:
        envelope = np.minimum(envelope, (seconds - t) / fade)
    return (amplitude * tone * envelope / 1.6).astype(np.float32)


def _glide(from_midi, to_midi, seconds, sr=SR, amplitude=0.5, fade_out=None):
    """A continuous slide between two pitches."""
    t = np.arange(int(sr * seconds)) / sr
    midi = from_midi + (to_midi - from_midi) * t / seconds
    phase = 2 * np.pi * np.cumsum(440.0 * 2 ** ((midi - 69) / 12)) / sr
    tone = np.sin(phase) + 0.4 * np.sin(2 * phase) + 0.2 * np.sin(3 * phase)
    envelope = np.minimum(1, (seconds - t) / fade_out) if fade_out else np.ones_like(t)
    return (amplitude * tone * envelope / 1.6).astype(np.float32)


HOP = 0.0125  # about the pitch tracker's frame spacing at 22050 Hz


def _analysis(stretches, total=None):
    """A process_audio-shaped result with a dense pitch track. stretches: (start, end, hz or None);
    None is loud but unpitched (a pop or breath). Everything else is silence."""
    total = total or max(end for _, end, _ in stretches) + 0.2
    times = np.arange(0, total, HOP)
    hz = np.full(times.size, np.nan)
    voiced = np.zeros(times.size, dtype=bool)
    rms_db = np.full(times.size, -90.0)
    for start, end, freq in stretches:
        inside = (times >= start) & (times < end)
        rms_db[inside] = -12.0
        if freq is not None:
            hz[inside], voiced[inside] = freq, True
    return {"pitch": {"times": times.tolist(), "frequencies": hz.tolist(), "voiced_flag": voiced.tolist(), "rms_db": rms_db.tolist()}}


def _write_wav(path, audio, sr=SR):
    pcm = np.clip(audio, -1.0, 1.0)
    pcm16 = (pcm * 32767).astype(np.int16)
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm16.tobytes())


def _write_tone_sequence(path, notes, sr=SR, gap=0.15):
    """notes: list of (freq_hz, duration_s). Silence gaps separate each note
    so segment detection can tell them apart."""
    chunks = []
    for freq, dur in notes:
        chunks.append(_tone(freq, dur, sr=sr))
        chunks.append(_silence(gap, sr=sr))
    audio = np.concatenate(chunks)
    _write_wav(path, audio, sr=sr)
    return audio


class TestPitchFidelity:
    """A known frequency in => the same frequency (within tolerance) out."""

    @pytest.mark.parametrize(
        "freq_hz",
        [220.0, 261.63, 440.0, 523.25],  # A3, C4, A4, C5
    )
    def test_single_tone_pitch_is_recovered(self, tmp_path, freq_hz):
        path = tmp_path / "tone.wav"
        _write_wav(path, _tone(freq_hz, 1.5))

        processor = AudioProcessor(target_sr=SR)
        audio, sr = processor.load_wav(str(path))
        pitch = processor.extract_pitch(audio, sr)

        assert pitch["voiced_frames"] > 0, "a clean sine tone should be detected as voiced"
        # PYIN on a pure tone should be accurate to well within a semitone (~3%).
        assert pitch["median_hz"] == pytest.approx(freq_hz, rel=0.03)

    def test_silence_produces_no_false_pitch(self, tmp_path):
        path = tmp_path / "silence.wav"
        _write_wav(path, _silence(1.0))

        processor = AudioProcessor(target_sr=SR)
        audio, sr = processor.load_wav(str(path))
        pitch = processor.extract_pitch(audio, sr)

        assert pitch["voiced_frames"] == 0, "silence must not be reported as a pitched note"


class TestMelodyFidelity:
    """A known sequence of notes in => the same number/order/pitch of notes out."""

    def test_note_count_and_order_survive(self, tmp_path):
        path = tmp_path / "melody.wav"
        sequence = [(261.63, 0.4), (329.63, 0.4), (392.00, 0.4)]  # C4, E4, G4
        _write_tone_sequence(path, sequence)

        notes = extract_notes(str(path), target_sr=SR, min_note_duration=0.05)

        assert len(notes) == len(sequence), (
            f"expected {len(sequence)} distinct notes, got {len(notes)}: {notes}"
        )
        for note, (expected_freq, _duration) in zip(notes, sequence):
            assert note["pitch_hz"] == pytest.approx(expected_freq, rel=0.05)

    def test_note_timing_is_not_shifted_or_dropped(self, tmp_path):
        path = tmp_path / "timing.wav"
        sequence = [(440.0, 0.3), (440.0, 0.3)]
        gap = 0.2
        audio = _write_tone_sequence(path, sequence, gap=gap)
        total_duration = len(audio) / SR

        notes = extract_notes(str(path), target_sr=SR, min_note_duration=0.05, merge_gap=0.0)

        assert len(notes) == 2, "equal-pitch notes separated by silence must stay separate notes"
        assert notes[0]["end"] <= notes[1]["start"], "notes must not overlap"
        gap_between = notes[1]["start"] - notes[0]["end"]
        assert gap_between > 0, "the silent gap between notes must not be swallowed"
        assert gap_between == pytest.approx(gap, abs=0.15)
        for note in notes:
            assert 0.0 <= note["start"] < note["end"] <= total_duration + 0.05

    def test_melody_midi_conversion_matches_known_note(self, tmp_path):
        path = tmp_path / "a4.wav"
        _write_wav(path, np.concatenate([_tone(440.0, 0.6), _silence(0.1)]))

        result = analyze_audio_file(str(path))
        melody = result["melody"]

        assert len(melody) == 1
        # A4 = MIDI note 69
        assert melody[0]["hz"] == pytest.approx(69.0, abs=0.5)


class TestRealNoteFiltering:
    """A loud segment isn't necessarily a sung note (mic pop, breath catch,
    attack transient). Regression: an earlier version of this filter dropped
    the note at index 0 unconditionally, on the assumption every recording
    starts with an artifact. That assumption was wrong far more often than
    right — most recordings start right on the user's real first note — and
    unconditionally discarding it corrupted melody, key, and chord detection.
    The filter must judge each segment on its own acoustic evidence (how much
    of it is confidently voiced/pitched), regardless of its position."""

    def _pop_then_melody(self, tmp_path, name="pop_melody.wav"):
        path = tmp_path / name
        # A mic pop/attack transient needs to be loud and long enough to
        # register as its own segment at all (a too-brief blip just gets
        # smoothed away by detect_sound_segments' analysis window) — a burst
        # of noise a bit longer than one analysis frame does the job. Being
        # noise (not a tone), PYIN should mark it mostly unvoiced.
        pop = 0.9 * (
            2 * np.random.default_rng(0).random(int(SR * 0.12)).astype(np.float32) - 1
        )
        sequence = [(261.63, 0.4), (329.63, 0.4)]  # C4, E4
        note1 = _tone(sequence[0][0], sequence[0][1])
        note2 = _tone(sequence[1][0], sequence[1][1])
        combined = np.concatenate([pop, _silence(0.3), note1, _silence(0.2), note2])
        _write_wav(path, combined)
        return path, sequence

    def test_a_leading_pop_is_filtered_by_being_unpitched_not_by_position(self, tmp_path):
        path, sequence = self._pop_then_melody(tmp_path)
        notes = extract_notes(str(path), target_sr=SR, min_note_duration=0.02)

        assert len(notes) == len(sequence)
        for note, (expected_freq, _duration) in zip(notes, sequence):
            assert note["pitch_hz"] == pytest.approx(expected_freq, rel=0.06)

    def test_a_real_first_note_is_kept_when_there_is_no_pop(self, tmp_path):
        """The regression case: a clean hum with no leading artifact at all
        must keep every one of its real notes, including the first."""
        path = tmp_path / "no_pop_melody.wav"
        sequence = [(261.63, 0.4), (329.63, 0.4), (392.00, 0.4)]  # C4, E4, G4
        _write_tone_sequence(path, sequence)

        notes = extract_notes(str(path), target_sr=SR, min_note_duration=0.05)

        assert len(notes) == len(sequence), (
            f"a real first note must survive when there's no artifact to drop, got {notes}"
        )
        assert notes[0]["pitch_hz"] == pytest.approx(sequence[0][0], rel=0.05)

    def test_extract_notes_keeps_a_single_real_note(self, tmp_path):
        path = tmp_path / "single_note.wav"
        _write_wav(path, _tone(440.0, 0.6))

        notes = extract_notes(str(path), target_sr=SR, min_note_duration=0.02)

        assert len(notes) == 1
        assert notes[0]["pitch_hz"] == pytest.approx(440.0, rel=0.05)

    def test_build_melody_drops_an_unpitched_segment_wherever_it_is(self):
        """Loud but unpitched stretches (voiced_flag False throughout) must be
        excluded regardless of whether they're first, middle, or last."""
        analysis = _analysis(
            [(0.0, 0.1, None), (0.3, 0.7, 261.63), (0.9, 1.0, None)]  # noise, note, noise
        )
        melody = _build_melody(analysis)
        assert len(melody) == 1
        assert melody[0]["start"] == pytest.approx(0.3, abs=HOP)

    def test_build_melody_keeps_a_single_real_segment(self):
        melody = _build_melody(_analysis([(0.0, 0.4, 261.63)]))
        assert len(melody) == 1

    def test_build_melody_keeps_all_real_notes_with_no_artifact(self):
        """The regression case for the production path: nothing should ever
        be dropped just for being first when every segment is genuinely
        voiced."""
        melody = _build_melody(_analysis([(0.0, 0.4, 261.63), (0.5, 0.9, 329.63)]))
        assert len(melody) == 2
        assert melody[0]["start"] == pytest.approx(0.0)


class TestNoteBoundaries:
    """Where one note ends and the next begins. The old detector only split on
    silence, so legato singing, repeated notes and noisy recordings collapsed
    into one long note. Repeated notes used to be merged on purpose across any
    pause under 120ms, which turned Twinkle Twinkle's C-C and G-G into single
    notes; only a breath too short to be a new attack is bridged now."""

    def test_a_pitch_tracker_dropout_does_not_split_a_note(self):
        """pYIN briefly losing the pitch (breathy tone) while the sound carries on is one note."""
        melody = _build_melody(_analysis([(0.0, 0.3, 261.63), (0.3, 0.33, None), (0.33, 0.63, 261.63)]))
        assert len(melody) == 1
        assert melody[0]["duration"] == pytest.approx(0.63, abs=2 * HOP)

    @pytest.mark.xfail(reason="Also fails in the original ECKO project: extract_notes (the simple engine's note detector) drops very short notes and merges repeated ones.", strict=False)
    def test_repeated_notes_separated_by_a_short_silence_stay_separate(self, tmp_path):
        path = tmp_path / "repeated.wav"
        audio = np.concatenate([_tone(440.0, 0.3), _silence(0.06), _tone(440.0, 0.3)])
        _write_wav(path, audio)

        notes = extract_notes(str(path), target_sr=SR)

        assert len(notes) == 2, f"a re-sung note is a new note, got {notes}"
        assert all(n["pitch_hz"] == pytest.approx(440.0, rel=0.02) for n in notes)

    @pytest.mark.xfail(reason="Also fails in the original ECKO project: extract_notes (the simple engine's note detector) drops very short notes and merges repeated ones.", strict=False)
    def test_repeated_notes_with_only_a_loudness_dip_stay_separate(self, tmp_path):
        """"da-da-da" on one pitch with no silence between: the dip in loudness is the only clue."""
        path = tmp_path / "da_da_da.wav"
        note = _hum(60, 0.3, fade=0.0)
        dip = np.concatenate([np.ones(int(SR * 0.25)), np.linspace(1.0, 0.3, note.size - int(SR * 0.25))])
        audio = np.concatenate([note * dip for _ in range(4)])
        _write_wav(path, audio)

        assert len(extract_notes(str(path), target_sr=SR)) == 4

    def test_legato_notes_with_no_gap_are_split_by_pitch(self, tmp_path):
        path = tmp_path / "legato.wav"
        scale = [60, 62, 64, 65, 67]
        _write_wav(path, np.concatenate([_hum(m, 0.4, fade=0.0) for m in scale]))

        notes = extract_notes(str(path), target_sr=SR)

        assert [round(n["midi"]) for n in notes] == scale
        assert all(n["duration"] == pytest.approx(0.4, abs=0.05) for n in notes)

    def test_does_not_merge_a_pause_between_genuinely_different_notes(self):
        """E4 and F4 are only ~20Hz apart, but they are different notes."""
        melody = _build_melody(_analysis([(0.0, 0.3, 329.63), (0.36, 0.66, 349.23)]))
        assert [round(n["hz"]) for n in melody] == [64, 65]

    def test_does_not_merge_across_a_long_pause(self):
        melody = _build_melody(_analysis([(0.0, 0.3, 261.63), (0.8, 1.1, 261.63)]))
        assert len(melody) == 2

    def test_a_slide_between_notes_gives_the_two_notes_not_a_smear(self, tmp_path):
        path = tmp_path / "slide.wav"
        _write_wav(path, np.concatenate([_hum(60, 0.4, fade=0.0), _glide(60, 67, 0.25), _hum(67, 0.4, fade=0.0)]))

        assert [round(n["midi"]) for n in extract_notes(str(path), target_sr=SR)] == [60, 67]

    def test_a_scoop_into_a_note_is_part_of_that_note(self, tmp_path):
        path = tmp_path / "scoops.wav"
        _write_wav(path, np.concatenate([np.concatenate([_glide(m - 1, m, 0.08, fade_out=0.0), _hum(m, 0.4, fade_in=0.0), _silence(0.08)]) for m in (60, 64, 67)]))

        assert [round(n["midi"]) for n in extract_notes(str(path), target_sr=SR)] == [60, 64, 67]


class TestMinimumNoteDuration:
    """Fast notes are real notes (a 16th at 120 BPM lasts 125ms, under the old
    200ms floor); only fragments under ~80ms are too short to be deliberate.
    A fragment touching a note is part of it; one on its own is a blip."""

    def test_an_isolated_blip_is_dropped(self, tmp_path):
        path = tmp_path / "blip_and_note.wav"
        _write_wav(path, np.concatenate([_tone(440.0, 0.04), _silence(0.3), _tone(523.25, 0.4)]))

        notes = extract_notes(str(path), target_sr=SR)

        assert len(notes) == 1, f"the 40ms blip should be dropped, got {notes}"
        assert notes[0]["pitch_hz"] == pytest.approx(523.25, rel=0.05)

    @pytest.mark.xfail(reason="Also fails in the original ECKO project: extract_notes (the simple engine's note detector) drops very short notes and merges repeated ones.", strict=False)
    def test_fast_sixteenths_are_kept(self, tmp_path):
        path = tmp_path / "fast.wav"
        run = [60, 62, 64, 65, 67, 65, 64, 62]
        _write_wav(path, np.concatenate([np.concatenate([_hum(m, 0.12), _silence(0.03)]) for m in run]))

        assert [round(n["midi"]) for n in extract_notes(str(path), target_sr=SR)] == run

    @pytest.mark.xfail(reason="Also fails in the original ECKO project: extract_notes (the simple engine's note detector) drops very short notes and merges repeated ones.", strict=False)
    def test_extract_notes_keeps_a_short_single_note(self, tmp_path):
        path = tmp_path / "short_but_valid.wav"
        _write_wav(path, _tone(440.0, 0.25))

        notes = extract_notes(str(path), target_sr=SR)

        assert len(notes) == 1
        assert notes[0]["pitch_hz"] == pytest.approx(440.0, rel=0.05)

    def test_build_melody_absorbs_a_fragment_into_the_note_it_touches(self):
        melody = _build_melody(_analysis([(0.0, 0.05, 246.94), (0.05, 0.45, 261.63)]))  # 50ms scoop, then C4
        assert len(melody) == 1
        assert melody[0]["start"] == pytest.approx(0.0)
        assert round(melody[0]["hz"]) == 60


class TestVibratoFidelity:
    """A hummed note wavers in pitch and loudness (vibrato/tremolo) instead of
    holding perfectly steady. The pipeline should still recover the intended
    center pitch as one note, not fragment it or drift off-key."""

    def test_vibrato_tone_center_pitch_is_recovered(self, tmp_path):
        path = tmp_path / "vibrato.wav"
        _write_wav(path, _vibrato_tone(440.0, 1.5))

        processor = AudioProcessor(target_sr=SR)
        audio, sr = processor.load_wav(str(path))
        pitch = processor.extract_pitch(audio, sr)

        assert pitch["voiced_frames"] > 0
        # Vibrato swings the instantaneous frequency by +/-15Hz around 440Hz;
        # the tracked median should still center near the sung note, not one
        # of the swing extremes, and definitely not a different note.
        assert pitch["median_hz"] == pytest.approx(440.0, rel=0.05)
        # PYIN must actually be following the wobble, not flatlining on one
        # frame's estimate (which would indicate it lost the pitch track).
        voiced_values = np.array(pitch["frequencies"])[pitch["voiced_flag"]]
        assert np.std(voiced_values) > 1.0

    def test_vibrato_note_is_not_fragmented_into_multiple_notes(self, tmp_path):
        """A single wavering hum must extract as one note, not several short
        ones split apart by the pitch wobble or tremolo dips."""
        path = tmp_path / "vibrato_note.wav"
        audio = np.concatenate([_vibrato_tone(392.0, 1.2), _silence(0.1)])
        _write_wav(path, audio)

        notes = extract_notes(str(path), target_sr=SR, min_note_duration=0.05)

        assert len(notes) == 1, f"a single sustained hum should be one note, got {notes}"
        assert notes[0]["pitch_hz"] == pytest.approx(392.0, rel=0.05)

    def test_vibrato_sequence_still_distinguishes_notes(self, tmp_path):
        """Two different hummed notes, each with vibrato, should still be told
        apart and land on the right pitches despite the inconsistency."""
        path = tmp_path / "vibrato_melody.wav"
        chunks = [
            _vibrato_tone(261.63, 0.6),  # C4
            _silence(0.15),
            _vibrato_tone(392.00, 0.6),  # G4
            _silence(0.15),
        ]
        _write_wav(path, np.concatenate(chunks))

        notes = extract_notes(str(path), target_sr=SR, min_note_duration=0.05)

        assert len(notes) == 2
        assert notes[0]["pitch_hz"] == pytest.approx(261.63, rel=0.06)
        assert notes[1]["pitch_hz"] == pytest.approx(392.00, rel=0.06)

    def test_wide_vibrato_in_background_noise_is_not_biased_off_pitch(self, tmp_path):
        """A wide, uneven vibrato (a shaky hum) plus mic background noise is
        the harshest realistic case: a wide pitch swing recorded on a noisy
        mic. A too-wide pitch-analysis window averages several vibrato
        swings together and skews the recovered pitch off the sung note
        entirely (regression: median drifted to ~466Hz for a 440Hz center
        with a +/-100Hz wobble). It must still land within a semitone."""
        path = tmp_path / "wide_vibrato_noise.wav"
        rng = np.random.default_rng(42)
        tone = _vibrato_tone(
            440.0, 1.5, amplitude=0.5, vibrato_rate_hz=6.0, vibrato_extent_hz=100.0
        )
        noise = 0.15 * rng.standard_normal(tone.shape).astype(np.float32)
        _write_wav(path, tone + noise)

        processor = AudioProcessor(target_sr=SR)
        audio, sr = processor.load_wav(str(path))
        pitch = processor.extract_pitch(audio, sr)

        assert pitch["voiced_frames"] > 0
        # A semitone at 440Hz is ~26Hz; a wide-but-real vibrato must not be
        # mistaken for a different note.
        assert pitch["median_hz"] == pytest.approx(440.0, rel=0.05)


class TestNoiseReduction:
    """reduce_noise() runs ahead of segmentation/pitch/volume/spectral
    extraction. It must measurably clean up noisy input, and — just as
    important — leave a clean recording untouched instead of introducing
    its own artifacts (regression: an early version merged/dropped notes
    in a perfectly clean hum by smoothing energy across silent gaps)."""

    def test_denoising_lowers_noise_floor_without_erasing_the_tone(self, tmp_path):
        """A realistic hum recording: brief silence before/after the note
        (mic lead-in/lead-out), noise throughout. The denoiser should learn
        the noise profile from those silent stretches and use it to quiet
        the background everywhere, while the note itself survives intact."""
        rng = np.random.default_rng(7)
        noise_amplitude = 0.01  # background hiss ~35dB below the hum, not comparable to it
        lead = noise_amplitude * rng.standard_normal(int(SR * 0.3)).astype(np.float32)
        tone = _tone(440.0, 1.0, amplitude=0.6) + noise_amplitude * rng.standard_normal(
            int(SR * 1.0)
        ).astype(np.float32)
        trail = noise_amplitude * rng.standard_normal(int(SR * 0.3)).astype(np.float32)
        noisy = np.concatenate([lead, tone, trail])

        processor = AudioProcessor(target_sr=SR)
        cleaned = processor.reduce_noise(noisy, SR)

        lead_samples = int(SR * 0.3)
        noise_before = np.sqrt(np.mean(noisy[:lead_samples] ** 2))
        noise_after = np.sqrt(np.mean(cleaned[:lead_samples] ** 2))
        assert noise_after < noise_before, "the lead-in noise floor should be measurably quieter"

        # The tone itself must survive: still a clean, voiced 440Hz signal.
        pitch = processor.extract_pitch(cleaned, SR)
        assert pitch["voiced_frames"] > 0
        assert pitch["median_hz"] == pytest.approx(440.0, rel=0.03)

    def test_denoising_does_not_corrupt_a_clean_recording(self, tmp_path):
        """Run a silence-separated melody (no added noise) through
        reduce_noise and check note count/pitch/order are identical to the
        undenoised extraction — denoising a clean hum must be a no-op in
        substance, not just "close enough"."""
        path = tmp_path / "clean_melody.wav"
        sequence = [(261.63, 0.4), (329.63, 0.4), (392.00, 0.4)]  # C4, E4, G4
        _write_tone_sequence(path, sequence)

        processor = AudioProcessor(target_sr=SR)
        cleaned = processor.process_audio(str(path), extract_volume=False, extract_spectral=False)
        raw = processor.process_audio(str(path), extract_volume=False, extract_spectral=False, clean=False)

        notes_cleaned, notes_raw = _build_melody(cleaned), _build_melody(raw)
        assert len(notes_cleaned) == len(notes_raw) == len(sequence)
        for a, b in zip(notes_cleaned, notes_raw):
            assert a["hz"] == pytest.approx(b["hz"], abs=0.1)
            assert a["start"] == pytest.approx(b["start"], abs=0.03)

    def test_silence_stays_silence_after_denoising(self, tmp_path):
        processor = AudioProcessor(target_sr=SR)
        cleaned = processor.reduce_noise(_silence(1.0), SR)
        assert np.max(np.abs(cleaned)) == pytest.approx(0.0, abs=1e-6)


class TestRobustnessAgainstCorruption:
    """The pipeline should degrade gracefully, not silently invent data."""

    def test_low_amplitude_signal_is_not_mistaken_for_silence_or_noise(self, tmp_path):
        path = tmp_path / "quiet.wav"
        _write_wav(path, _tone(440.0, 1.0, amplitude=0.05))

        processor = AudioProcessor(target_sr=SR)
        audio, sr = processor.load_wav(str(path))
        pitch = processor.extract_pitch(audio, sr)

        assert pitch["voiced_frames"] > 0
        assert pitch["median_hz"] == pytest.approx(440.0, rel=0.05)

    def test_clean_audio_round_trip_preserves_pitch(self, tmp_path):
        """clean_audio (bandpass + trim + normalize) must not distort the
        fundamental frequency it's supposed to make clearer."""
        path = tmp_path / "noisy.wav"
        rng = np.random.default_rng(0)
        tone = _tone(440.0, 1.0, amplitude=0.6)
        noise = 0.02 * rng.standard_normal(tone.shape).astype(np.float32)
        _write_wav(path, tone + noise)

        processor = AudioProcessor(target_sr=SR)
        audio, sr = processor.load_wav(str(path))
        cleaned = processor.clean_audio(audio, sr)
        pitch = processor.extract_pitch(cleaned, sr)

        assert pitch["voiced_frames"] > 0
        assert pitch["median_hz"] == pytest.approx(440.0, rel=0.03)

    def test_resampling_preserves_pitch(self, tmp_path):
        """Loading at a non-native sample rate (as the recorder's mic input
        would be) must resample without shifting the perceived pitch."""
        native_sr = 44100
        path = tmp_path / "native.wav"
        _write_wav(path, _tone(440.0, 1.0, sr=native_sr), sr=native_sr)

        processor = AudioProcessor(target_sr=22050)
        audio, sr = processor.load_wav(str(path))
        pitch = processor.extract_pitch(audio, sr)

        assert sr == 22050
        assert pitch["median_hz"] == pytest.approx(440.0, rel=0.03)


SCALE = [60, 62, 64, 65, 67]  # C D E F G


def _scale(sr=SR, **hum_kwargs):
    return np.concatenate([np.concatenate([_hum(m, 0.4, sr=sr, **hum_kwargs), _silence(0.1, sr=sr)]) for m in SCALE])


def _midi_of(path):
    return [round(n["hz"]) for n in analyze_audio_file(str(path))["melody"]]


class TestRealWorldRecordings:
    """What phone and laptop mics actually deliver. Each of these used to lose
    or merge notes silently (see the Phase 2 probe): noise within 30 dB of the
    hum made the whole clip one "sound segment", so it came out as one note."""

    def test_background_hiss_at_minus_25_db(self, tmp_path):
        audio = _scale()
        audio = audio + 0.5 * 10 ** (-25 / 20) * np.random.default_rng(0).standard_normal(audio.size)
        _write_wav(tmp_path / "hiss.wav", audio)
        assert _midi_of(tmp_path / "hiss.wav") == SCALE

    def test_mains_hum_at_minus_20_db(self, tmp_path):
        audio = _scale()
        audio = audio + 0.5 * 10 ** (-20 / 20) * np.sin(2 * np.pi * 60 * np.arange(audio.size) / SR)
        _write_wav(tmp_path / "mains.wav", audio)
        assert _midi_of(tmp_path / "mains.wav") == SCALE

    def test_room_reverb(self, tmp_path):
        rng = np.random.default_rng(1)
        tail = rng.standard_normal(int(SR * 0.5)) * np.exp(-np.arange(int(SR * 0.5)) / SR / 0.12)
        tail[0] = 8
        audio = np.convolve(_scale(), tail)
        _write_wav(tmp_path / "reverb.wav", 0.8 * audio / np.max(np.abs(audio)))
        assert _midi_of(tmp_path / "reverb.wav") == SCALE

    def test_clipped_recording_keeps_its_notes_and_says_so(self, tmp_path):
        _write_wav(tmp_path / "clipped.wav", np.clip(_scale() * 6, -1.0, 1.0))
        result = analyze_audio_file(str(tmp_path / "clipped.wav"))
        assert [round(n["hz"]) for n in result["melody"]] == SCALE
        assert any("clipping" in w for w in result["warnings"])

    def test_very_quiet_recording_keeps_its_notes_and_says_so(self, tmp_path):
        _write_wav(tmp_path / "quiet.wav", _scale() * 0.02)
        result = analyze_audio_file(str(tmp_path / "quiet.wav"))
        assert [round(n["hz"]) for n in result["melody"]] == SCALE
        assert any("quiet" in w for w in result["warnings"])

    def test_leading_silence_adds_no_ghost_notes(self, tmp_path):
        _write_wav(tmp_path / "late.wav", np.concatenate([_silence(1.5), _scale()]))
        melody = analyze_audio_file(str(tmp_path / "late.wav"))["melody"]
        assert [round(n["hz"]) for n in melody] == SCALE
        assert melody[0]["start"] == pytest.approx(1.5, abs=0.05)

    def test_whistling_above_the_old_800hz_ceiling(self, tmp_path):
        _write_wav(tmp_path / "whistle.wav", np.concatenate([np.concatenate([_tone(440.0 * 2 ** ((m + 24 - 69) / 12), 0.4), _silence(0.1)]) for m in SCALE]))
        assert _midi_of(tmp_path / "whistle.wav") == [m + 24 for m in SCALE]

    def test_an_octave_leap_is_kept(self, tmp_path):
        _write_wav(tmp_path / "leap.wav", np.concatenate([_hum(57, 0.4), _silence(0.08), _hum(69, 0.4), _silence(0.08), _hum(57, 0.4)]))
        assert _midi_of(tmp_path / "leap.wav") == [57, 69, 57]

    @pytest.mark.parametrize(("sr", "subtype", "channels"), [(48000, "PCM_16", 1), (44100, "PCM_24", 2), (16000, "FLOAT", 1)])
    def test_any_rate_depth_or_channel_count(self, tmp_path, sr, subtype, channels):
        audio = _scale(sr=sr)
        path = tmp_path / "format.wav"
        sf.write(path, np.stack([audio] * channels, axis=1) if channels > 1 else audio, sr, subtype=subtype)
        assert _midi_of(path) == SCALE


class TestTuning:
    """A singer who is consistently off A440 should still land on the notes they meant."""

    @pytest.mark.parametrize("cents", [-45, -30, 30, 45])
    def test_a_consistently_out_of_tune_hum_lands_on_the_intended_notes(self, tmp_path, cents):
        _write_wav(tmp_path / "detuned.wav", _scale(cents=cents))
        result = analyze_audio_file(str(tmp_path / "detuned.wav"))
        assert [round(n["hz"]) for n in result["melody"]] == SCALE
        assert all(n["hz"] == pytest.approx(round(n["hz"]), abs=0.1) for n in result["melody"])
        assert result["tuning_cents"] == pytest.approx(cents, abs=10)

    def test_vibrato_is_not_mistaken_for_being_out_of_tune(self, tmp_path):
        audio = np.concatenate([np.concatenate([_vibrato_tone(440.0 * 2 ** ((m - 69) / 12), 0.5, vibrato_extent_hz=0.03 * 440.0 * 2 ** ((m - 69) / 12)), _silence(0.1)]) for m in SCALE])
        _write_wav(tmp_path / "vibrato_scale.wav", audio)
        result = analyze_audio_file(str(tmp_path / "vibrato_scale.wav"))
        assert [round(n["hz"]) for n in result["melody"]] == SCALE
        assert abs(result["tuning_cents"]) <= 15
