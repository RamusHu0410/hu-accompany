import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:hu_accomponist/integrations/server/ServerDiscovery.dart';
import 'package:hu_accomponist/integrations/feedback/Pull_back_phrase.dart';
import 'package:hu_accomponist/src/rust/models.dart';

/// Sends one phrase to backend/feedback_generator's phase-1 endpoint.
///
/// Unlike the placeholder version of this file, POST /api/feedback/phrase
/// is synchronous — the backend judges the phrase and returns its full
/// PhraseReport (see Pull_back_Phrase.dart) in the same response. There's
/// no separate "pull" step for an individual phrase; Pull_back_Phrase.dart
/// is reserved for the one thing that IS a separate request: the
/// whole-session summary once recording is done.
class PhraseUploadService {
  PhraseUploadService._();

  static const String _sendPhrasePath = '/api/feedback/phrase';
  static const Duration _sendTimeout = Duration(seconds: 30);

  /// [sessionId] should be null for a phrase 1 of a new recording (the
  /// backend defaults the session to today's date + piece title) — take
  /// the `sessionId` off THAT response and pass it in here for every
  /// later phrase in the same recording, so they land in the same
  /// session directory instead of each defaulting independently.
  ///
  /// [expectedNotes] is the ground-truth note list for this phrase's bars
  /// (note_id/pitch_hz/start_time_ms/end_time_ms/duration_ms per the
  /// README) — TODO: wire this in from wherever your OMR output
  /// (/api/score/process or /api/score/process-omr's notes_json) ends up
  /// stored for the currently loaded piece; this file has no opinion on
  /// where that lives, it just needs the list for the bars this phrase
  /// covers.
  ///
  /// [userNotes] is what Rust detected the player actually play, straight
  /// from notesStream() (see Draggable_Recorder_Button.dart).
  ///
  /// [barBoxes] is optional — pass pdf_processor's `<Piece>_bars.json`
  /// content through here if you want `box` populated on the feedback
  /// that comes back; omit it and every `box` is null.
  ///
  /// Returns null on any network/parsing failure — logged, not thrown, so
  /// a dropped phrase doesn't crash the recording session.
  static Future<PhraseReport?> sendPhrase({
    String? sessionId,
    required int phraseNumber,
    required double bpm,
    required String timeSignature,
    required PieceInfo piece,
    required List<Map<String, dynamic>> expectedNotes,
    required List<Notes> userNotes,
    List<Map<String, dynamic>>? barBoxes,
  }) async {
    final baseUrl = await ServerDiscovery.resolveBaseUrl();
    if (baseUrl == null) {
      debugPrint(
        '[Diagnostics] phrase $phraseNumber FAILED: no backend found on this '
        'network. Will retry discovery on the next phrase.',
      );
      return null;
    }

    final body = jsonEncode({
      if (sessionId != null) 'session_id': sessionId,
      'phrase': phraseNumber,
      'timing': {'bpm': bpm, 'time_signature': timeSignature},
      'piece': piece.toJson(),
      'expected_notes': expectedNotes,
      'user_notes': userNotes.map(_userNoteToJson).toList(),
      if (barBoxes != null) 'bar_boxes': barBoxes,
    });

    final stopwatch = Stopwatch()..start();
    debugPrint(
      '[Diagnostics] phrase $phraseNumber -> POST $baseUrl$_sendPhrasePath '
      '(session=${sessionId ?? "new"}, ${userNotes.length} note(s))',
    );

    var response = await _post(baseUrl, body);

    // Same "stale cached address" recovery used elsewhere: a null
    // response means the request itself failed, so re-discover and retry
    // once before giving up on this phrase.
    if (response == null) {
      ServerDiscovery.invalidateCache();
      final freshBaseUrl = await ServerDiscovery.resolveBaseUrl(
        forceRefresh: true,
      );
      if (freshBaseUrl == null) {
        debugPrint(
          '[Diagnostics] phrase $phraseNumber FAILED: backend not found on '
          'rediscovery. Will retry on the next phrase.',
        );
        return null;
      }
      debugPrint(
        '[Diagnostics] rediscovered backend at $freshBaseUrl — retrying '
        'phrase $phraseNumber once.',
      );
      response = await _post(freshBaseUrl, body);
    }

    if (response == null) {
      debugPrint(
        '[Diagnostics] phrase $phraseNumber FAILED after ${stopwatch.elapsedMilliseconds}ms '
        '(network error). Will retry on the next phrase.',
      );
      return null;
    }

    if (response.statusCode != 200) {
      debugPrint(
        '[Diagnostics] phrase $phraseNumber FAILED: HTTP ${response.statusCode} '
        'in ${stopwatch.elapsedMilliseconds}ms — ${response.body}',
      );
      return null;
    }

    try {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      final report = PhraseReport.fromJson(decoded);
      debugPrint(
        '[Diagnostics] phrase $phraseNumber OK: HTTP 200 in '
        '${stopwatch.elapsedMilliseconds}ms, overall=${report.scores.overall}, '
        '${report.feedback.length} finding(s), session=${report.sessionId}',
      );
      return report;
    } catch (error) {
      debugPrint('[Diagnostics] phrase $phraseNumber: could not parse response — $error');
      return null;
    }
  }

  static Future<http.Response?> _post(String baseUrl, String body) async {
    final uri = Uri.parse('$baseUrl$_sendPhrasePath');
    try {
      return await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: body,
          )
          .timeout(_sendTimeout);
    } on Exception catch (error) {
      debugPrint('[PhraseUpload] Send failed: $error');
      return null;
    }
  }

  /// Maps one Rust-detected note to the wire shape the backend's
  /// `_parse_user_note` expects.
  ///
  /// `pitch_hz`, `start_time_ms`, `end_time_ms` and `duration_ms` are read
  /// with `raw["..."]` on the backend, so all four keys must be present or
  /// the whole phrase is rejected with InvalidNoteData (400). Rust types
  /// three of them as Option<f32>, so a null has to be resolved here rather
  /// than passed through: end is derived from start+duration (or duration
  /// from start..end) where possible, and anything still unknown falls back
  /// to 0 with a diagnostic, since the backend sorts on start_time_ms and
  /// cannot order a null.
  ///
  /// `note_id` and `has_accent` are optional (`raw.get`) and are sent only
  /// when Rust supplied them. `isEnd` is a stream-control flag marking the
  /// last note of a phrase, not performance data, so it is not sent.
  static Map<String, dynamic> _userNoteToJson(Notes note) {
    final start = note.startTimeMs;
    final end = note.endTimeMs;
    final duration = note.durationMs;

    final resolvedStart = start ?? 0;
    final resolvedDuration =
        duration ?? ((end != null && start != null) ? end - start : 0);
    final resolvedEnd = end ?? (resolvedStart + resolvedDuration);

    if (start == null || (end == null && duration == null)) {
      debugPrint(
        '[Diagnostics] note ${note.noteId} arrived without timing '
        '(start=$start end=$end duration=$duration) — sent as '
        'start=$resolvedStart end=$resolvedEnd duration=$resolvedDuration; '
        'rhythm/tempo scoring for this phrase will be unreliable.',
      );
    }

    return {
      'note_id': note.noteId.toInt(),
      'pitch_hz': note.pitchHz,
      'start_time_ms': resolvedStart,
      'end_time_ms': resolvedEnd,
      'duration_ms': resolvedDuration,
      if (note.hasAccent != null) 'has_accent': note.hasAccent,
    };
  }
}
