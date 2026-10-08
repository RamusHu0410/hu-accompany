import 'dart:math' as math;

/// One written note of an exercise: a pitch (MIDI number, before octave
/// transposition) and how many beats it lasts.
class ExerciseStep {
  final int midi;
  final int beats;
  const ExerciseStep(this.midi, [this.beats = 1]);
}

/// A note of an exercise laid out on the timeline at a chosen tempo and
/// octave. This is the score both Rust and the backend judge against.
class ExpectedNote {
  final int noteId;
  final int midi;
  final double pitchHz;
  final double startMs;
  final double durationMs;

  /// Zero-based bar this note sits in. A bar is one phrase.
  final int bar;

  /// True on the last note of its bar. Rust copies this onto what it
  /// detects, which is how a finished phrase is recognised.
  final bool isEnd;

  const ExpectedNote({
    required this.noteId,
    required this.midi,
    required this.pitchHz,
    required this.startMs,
    required this.durationMs,
    required this.bar,
    required this.isEnd,
  });

  double get endMs => startMs + durationMs;

  String get name => Exercise.noteName(midi);

  /// The shape the backend's `/api/feedback/phrase` requires for
  /// `expected_notes` (all five keys are mandatory there).
  Map<String, dynamic> toBackendJson() => {
    'note_id': noteId,
    'pitch_hz': pitchHz,
    'start_time_ms': startMs,
    'end_time_ms': endMs,
    'duration_ms': durationMs,
  };

  /// The shape of native_ffi's `Notes` struct, for `initSession`.
  Map<String, dynamic> toRustJson() => {
    'note_id': noteId,
    'pitch_hz': pitchHz,
    'start_time_ms': startMs,
    'end_time_ms': endMs,
    'duration_ms': durationMs,
    'is_end': isEnd,
    'vibrato_depth': null,
    'pedal_action': null,
    'has_accent': null,
    'markings': null,
  };
}

/// A short built-in piece with exactly known notes.
///
/// These exist because the pipeline that should read notes off a PDF
/// (`/api/score/process`) does not work yet, and Rust cannot listen for
/// anything until it is given the notes to expect. With an exercise, the
/// microphone, Rust detection and Python judging are all real; only the
/// score comes from here instead of from OMR.
class Exercise {
  final String id;
  final String title;
  final String description;

  /// Steps written around C4 (MIDI 60); transposed by the chosen octave.
  final List<ExerciseStep> steps;

  const Exercise({
    required this.id,
    required this.title,
    required this.description,
    required this.steps,
  });

  static const int beatsPerBar = 4;
  static const String timeSignature = '4/4';

  static const List<int> tempos = [60, 80, 100];
  static const List<int> octaves = [3, 4, 5];

  /// Octave 5 is the default because this detector resolves pitch in
  /// ~47 Hz steps: a semitone around C5 spans about two thirds of a step,
  /// but around C4 only a third, so higher is judged more reliably.
  static const int defaultOctave = 5;
  static const int defaultTempo = 60;

  static const List<Exercise> all = [
    Exercise(
      id: 'c-major-scale',
      title: 'C major scale',
      description: 'Up and back down, one note per beat.',
      steps: [
        ExerciseStep(60), ExerciseStep(62), ExerciseStep(64), ExerciseStep(65),
        ExerciseStep(67), ExerciseStep(69), ExerciseStep(71), ExerciseStep(72),
        ExerciseStep(72), ExerciseStep(71), ExerciseStep(69), ExerciseStep(67),
        ExerciseStep(65), ExerciseStep(64), ExerciseStep(62), ExerciseStep(60),
      ],
    ),
    Exercise(
      id: 'c-major-arpeggio',
      title: 'C major arpeggio',
      description: 'C, E, G, C up and down.',
      steps: [
        ExerciseStep(60), ExerciseStep(64), ExerciseStep(67), ExerciseStep(72),
        ExerciseStep(72), ExerciseStep(67), ExerciseStep(64), ExerciseStep(60),
      ],
    ),
    Exercise(
      id: 'twinkle',
      title: 'Twinkle, Twinkle',
      description: 'The opening phrase, with held notes.',
      steps: [
        ExerciseStep(60), ExerciseStep(60), ExerciseStep(67), ExerciseStep(67),
        ExerciseStep(69), ExerciseStep(69), ExerciseStep(67, 2),
        ExerciseStep(65), ExerciseStep(65), ExerciseStep(64), ExerciseStep(64),
        ExerciseStep(62), ExerciseStep(62), ExerciseStep(60, 2),
      ],
    ),
  ];

  static double midiToHz(int midi) => 440.0 * math.pow(2, (midi - 69) / 12);

  static const _names = [
    'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B',
  ];

  static String noteName(int midi) => '${_names[midi % 12]}${midi ~/ 12 - 1}';

  /// Lays the exercise out in time. The first note starts at 0 ms because
  /// Rust starts its clock at the moment it hears that first note.
  List<ExpectedNote> layout({required int bpm, required int octave}) {
    final beatMs = 60000.0 / bpm;
    final shift = (octave - 4) * 12;
    final notes = <ExpectedNote>[];
    var beat = 0;
    for (var i = 0; i < steps.length; i++) {
      final step = steps[i];
      final midi = step.midi + shift;
      final bar = beat ~/ beatsPerBar;
      final nextBeat = beat + step.beats;
      final lastInBar =
          i == steps.length - 1 || nextBeat ~/ beatsPerBar != bar;
      notes.add(
        ExpectedNote(
          noteId: i + 1,
          midi: midi,
          pitchHz: midiToHz(midi),
          startMs: beat * beatMs,
          durationMs: step.beats * beatMs,
          bar: bar,
          isEnd: lastInBar,
        ),
      );
      beat = nextBeat;
    }
    return notes;
  }

  /// native_ffi's `PieceData`, as JSON for `initSession`. Rust parses this
  /// strictly, so every field it declares is present with its exact type:
  /// `curr_phase` must be 0 or 1 or Rust ignores the audio, and `timing`
  /// needs `beat_unit`, not the `time_signature` the backend uses.
  Map<String, dynamic> toPieceData({required int bpm, required int octave}) => {
    'piece_name': title,
    'curr_phase': 0,
    'instrument': null,
    'curr_music_phrase': 0,
    'timing': {'bpm': bpm.toDouble(), 'beat_unit': 4},
    'notes': layout(bpm: bpm, octave: octave)
        .map((n) => n.toRustJson())
        .toList(),
  };
}
