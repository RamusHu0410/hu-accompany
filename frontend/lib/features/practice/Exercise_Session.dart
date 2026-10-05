import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'package:hu_accomponist/features/practice/Exercise.dart';
import 'package:hu_accomponist/features/practice/Phrase_Assembler.dart';
import 'package:hu_accomponist/integrations/audio/Rust_Session.dart';
import 'package:hu_accomponist/integrations/feedback/Phrase_send2_server.dart';
import 'package:hu_accomponist/integrations/feedback/Pull_back_phrase.dart';
import 'package:hu_accomponist/src/rust/models.dart';

/// One run through an exercise: loads it into Rust, counts the player in,
/// and turns what Rust hears into phrases for the backend.
///
/// UI state ([countIn], [downbeat]) is exposed through [ChangeNotifier] so
/// only the exercise view rebuilds on each beat, not the practice screen.
class ExerciseSession extends ChangeNotifier {
  ExerciseSession({
    required this.exercise,
    required this.bpm,
    required this.octave,
    required this.onReport,
  }) : notes = exercise.layout(bpm: bpm, octave: octave);

  final Exercise exercise;
  final int bpm;
  final int octave;
  final List<ExpectedNote> notes;

  /// Called with each judged phrase, in order.
  final void Function(PhraseReport report) onReport;

  static const int countInBeats = 4;

  double get beatMs => 60000.0 / bpm;

  /// The count-in beat being shown (1..[countInBeats]), or null.
  int? countIn;

  /// When the first note should be played. Drives the metronome pulse and
  /// the highlighted note. Null outside a recording.
  DateTime? downbeat;

  PhraseAssembler _assembler = PhraseAssembler(const []);
  String? _sessionId;
  Future<void> _sendQueue = Future.value();
  Timer? _downbeatTimer;
  bool _disposed = false;

  /// Runs before capture starts. Loads the exercise into Rust, then counts
  /// the player in. Returns an error message, or null to go ahead.
  ///
  /// Resolves at the start of the last count-in beat, one beat early, so
  /// the microphone is already running when the first note is played. Exact
  /// timing matters less than it looks: Rust starts its clock when it hears
  /// the first note, not when capture begins.
  Future<String?> prepare() async {
    final error = await RustSession.load(
      exercise.toPieceData(bpm: bpm, octave: octave),
    );
    if (error != null) return error;

    _assembler = PhraseAssembler(notes);
    _sessionId = null;
    final beat = Duration(microseconds: (beatMs * 1000).round());

    for (var i = 1; i < countInBeats; i++) {
      if (_disposed) return 'cancelled';
      _set(countIn: i);
      // Haptics only before capture starts: once the microphone is live, a
      // vibration can register as sound.
      HapticFeedback.mediumImpact();
      await Future<void>.delayed(beat);
    }

    if (_disposed) return 'cancelled';
    downbeat = DateTime.now().add(beat);
    _set(countIn: countInBeats);
    _downbeatTimer = Timer(beat, () => _set(countIn: null));
    return null;
  }

  /// A batch from Rust's notesStream.
  void onRustBatch(List<Notes> batch) {
    _enqueue(_assembler.add(batch));
  }

  /// Recording stopped: judge whatever is still unsent, including the note
  /// that may still have been sounding.
  Future<void> finish() async {
    _downbeatTimer?.cancel();
    downbeat = null;
    _set(countIn: null);
    _enqueue(_assembler.flush(await RustSession.leftovers()));
    await _sendQueue;
  }

  /// Phrases are sent one at a time, in order, so each can reuse the
  /// session id the backend assigned to the first.
  void _enqueue(List<AssembledPhrase> phrases) {
    for (final phrase in phrases) {
      _sendQueue = _sendQueue.then((_) => _send(phrase));
    }
  }

  Future<void> _send(AssembledPhrase phrase) async {
    debugPrint(
      '[Diagnostics] bar ${phrase.number}: ${phrase.userNotes.length} heard / '
      '${phrase.expectedNotes.length} written',
    );
    final report = await PhraseUploadService.sendPhrase(
      sessionId: _sessionId,
      phraseNumber: phrase.number,
      bpm: bpm.toDouble(),
      timeSignature: Exercise.timeSignature,
      piece: PieceInfo(
        title: exercise.title,
        composer: 'Exercise',
        composedDate: '',
      ),
      expectedNotes: phrase.expectedNotes,
      userNotes: phrase.userNotes,
    );
    if (report == null || _disposed) return;
    _sessionId ??= report.sessionId;
    onReport(report);
  }

  void _set({required int? countIn}) {
    if (_disposed) return;
    this.countIn = countIn;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _downbeatTimer?.cancel();
    super.dispose();
  }
}
