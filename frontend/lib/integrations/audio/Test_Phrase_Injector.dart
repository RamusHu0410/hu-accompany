import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle;

import 'package:hu_accomponist/integrations/feedback/Pull_back_phrase.dart';
import 'package:hu_accomponist/src/rust/api.dart';

/// Everything the sample fixture supplies for one test phrase.
///
/// The app has no OMR pipeline, so nothing normally populates
/// `expected_notes`, `bpm` or the piece identity — and the backend rejects a
/// phrase that has no ground truth to judge against. The fixture carries all
/// of it, so a test run can stand in for the missing pipeline rather than
/// posting a request the server is bound to refuse.
class TestPhraseSample {
  final List<Map<String, dynamic>> expectedNotes;
  final PieceInfo piece;
  final double bpm;
  final String timeSignature;

  const TestPhraseSample({
    required this.expectedNotes,
    required this.piece,
    required this.bpm,
    required this.timeSignature,
  });
}

/// Test-only: feeds a canned phrase through the real Rust pipeline.
///
/// This is not a shortcut around Rust — it is the opposite. The notes are
/// handed to `inject_test_phrase` on the Rust side, which pushes them into
/// the same `notes_stream` sink the microphone path feeds. Dart receives
/// them through the ordinary `notesStream()` subscription the recorder sets
/// up, uploads them to the Python judge, and renders the verdict. Every hop
/// after pitch detection is the real one; only the microphone and the DSP
/// are stood in for.
abstract final class TestPhraseInjector {
  /// The same fixture the backend's `post_sample_phrase.sh` posts, so a run
  /// through the app and a run through curl are judged on identical input.
  /// Deliberately an imperfect performance.
  static const String samplePath = 'assets/sample/phrase_imperfect.json';

  static Future<String> _load() => rootBundle.loadString(samplePath);

  /// Reads the fixture's ground truth: what the app would have known if the
  /// OMR pipeline existed.
  static Future<TestPhraseSample?> loadSample() async {
    try {
      final decoded = jsonDecode(await _load()) as Map<String, dynamic>;
      final timing = decoded['timing'] as Map<String, dynamic>? ?? const {};
      return TestPhraseSample(
        expectedNotes: (decoded['expected_notes'] as List<dynamic>? ?? const [])
            .cast<Map<String, dynamic>>(),
        piece: PieceInfo.fromJson(
          decoded['piece'] as Map<String, dynamic>? ?? const {},
        ),
        bpm: (timing['bpm'] as num?)?.toDouble() ?? 96,
        timeSignature: timing['time_signature'] as String? ?? '4/4',
      );
    } catch (e) {
      debugPrint('[Diagnostics] inject: could not read $samplePath — $e');
      return null;
    }
  }

  /// Hands the fixture's `user_notes` to Rust. Returns Rust's own status
  /// string: how many notes it emitted, or why none — notably "no listener"
  /// when nothing has subscribed to `notesStream()` yet, which is the case
  /// until recording has been started once.
  static Future<String> injectSample() async {
    final String json;
    try {
      json = await _load();
    } catch (e) {
      final message = 'could not load $samplePath — $e';
      debugPrint('[Diagnostics] inject: $message');
      return message;
    }

    try {
      final status = await injectTestPhrase(jsonData: json);
      debugPrint('[Diagnostics] inject: $status');
      return status;
    } catch (e) {
      // Reached when the Rust library is not linked into this build at all,
      // which is the situation on macOS.
      final message = 'Rust bridge unavailable — $e';
      debugPrint('[Diagnostics] inject: $message');
      return message;
    }
  }
}
