import 'dart:convert';

import 'package:flutter/foundation.dart';

import 'package:hu_accomponist/integrations/audio/Rust_Bridge.dart';
import 'package:hu_accomponist/src/rust/api.dart';
import 'package:hu_accomponist/src/rust/models.dart';

/// Loads a piece into the Rust audio engine and reads back what it holds.
///
/// Rust only listens for notes of the active piece — with none loaded, the
/// microphone runs but nothing is ever detected — so a piece has to be
/// loaded before every recording. Loading also clears whatever a previous
/// recording left behind.
abstract final class RustSession {
  /// Loads [pieceData] (native_ffi's `PieceData` shape). Returns null on
  /// success, or a message explaining why it could not be loaded.
  static Future<String?> load(Map<String, dynamic> pieceData) async {
    await RustBridge.ensureInitialized();
    if (!RustBridge.isAvailable) {
      return 'The audio engine is not available in this build.';
    }
    try {
      await initSession(jsonData: jsonEncode(pieceData));
      debugPrint(
        '[Diagnostics] rust: loaded "${pieceData['piece_name']}" '
        '(${(pieceData['notes'] as List).length} notes)',
      );
      return null;
    } catch (e) {
      // Rust parses the piece strictly; a malformed one comes back here as
      // an error rather than taking the app down.
      debugPrint('[Diagnostics] rust: could not load piece — $e');
      return 'The audio engine rejected this exercise: $e';
    }
  }

  /// Entries Rust gathered but has not sent. Rust only sends when a note
  /// ends, so a note still sounding when recording stops would otherwise be
  /// lost.
  static Future<List<Notes>> leftovers() async {
    if (!RustBridge.isAvailable) return const [];
    try {
      final decoded = jsonDecode(await getUserData());
      if (decoded is! List) return const [];
      final notes = decoded
          .whereType<Map<String, dynamic>>()
          .map(notesFromJson)
          .toList();
      debugPrint('[Diagnostics] rust: ${notes.length} unsent entr(ies) at stop');
      return notes;
    } catch (e) {
      debugPrint('[Diagnostics] rust: could not read leftover notes — $e');
      return const [];
    }
  }

  static double? _double(Object? v) => (v as num?)?.toDouble();

  @visibleForTesting
  static Notes notesFromJson(Map<String, dynamic> j) => Notes(
    noteId: BigInt.from((j['note_id'] as num).toInt()),
    pitchHz: _double(j['pitch_hz']) ?? 0,
    startTimeMs: _double(j['start_time_ms']),
    endTimeMs: _double(j['end_time_ms']),
    durationMs: _double(j['duration_ms']),
    isEnd: j['is_end'] as bool? ?? false,
    vibratoDepth: _double(j['vibrato_depth']),
    pedalAction: j['pedal_action'] as String?,
    hasAccent: j['has_accent'] as bool?,
    markings: j['markings'] as String?,
    volume: _double(j['volume']),
  );
}
