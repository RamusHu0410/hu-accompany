import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'ServerDiscovery.dart';
import '../utils/Pull_back_Phrase.dart';
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
        '[PhraseUpload] No backend found on network — dropping phrase $phraseNumber.',
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
          '[PhraseUpload] Backend unreachable after retry — dropping phrase $phraseNumber.',
        );
        return null;
      }
      response = await _post(freshBaseUrl, body);
    }

    if (response == null) {
      debugPrint(
        '[PhraseUpload] Phrase $phraseNumber failed to send (network error).',
      );
      return null;
    }

    if (response.statusCode != 200) {
      debugPrint(
        '[PhraseUpload] Phrase $phraseNumber rejected: '
        '${response.statusCode} — ${response.body}',
      );
      return null;
    }

    try {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      return PhraseReport.fromJson(decoded);
    } catch (error) {
      debugPrint('[PhraseUpload] Could not parse response: $error');
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

  // TODO: Notes is the flutter_rust_bridge-generated model from
  // src/rust/models.dart, whose real fields weren't available while
  // wiring this up. The backend wants note_id/pitch_hz/start_time_ms/
  // end_time_ms/duration_ms per note (see the README's curl example) —
  // replace the placeholder below with the actual field names once
  // you can see that generated file.
  static Map<String, dynamic> _userNoteToJson(Notes note) {
    return {
      // 'note_id': note.noteId,
      // 'pitch_hz': note.pitchHz,
      // 'start_time_ms': note.startTimeMs,
      // 'end_time_ms': note.startTimeMs + note.durationMs,
      // 'duration_ms': note.durationMs,
      'raw': note.toString(), // placeholder until real fields are wired in
    };
  }
}