import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'ServerDiscovery.dart';
import 'package:hu_accomponist/src/rust/models.dart';

/// Sends one recorded phrase's raw note data to the backend the moment
/// Rust finishes analyzing it — this is the "constant push" half of the
/// new recording pipeline, mirrored on the pull side by
/// PhraseFeedbackService in Pull_back_Phrase.dart.
///
/// Deliberately kept in its own file, separate from the PDF push/pull
/// pair in Pulling_Back_Data.dart / Send_Strings_2Server.dart, so the two
/// pipelines (score fetching vs. live practice scoring) never overlap.
///
/// Same discovery + retry-once-on-stale-address pattern as the existing
/// services — see ServerDiscovery.dart.
class PhraseUploadService {
  PhraseUploadService._();

  // PLACEHOLDER — this endpoint does not exist on the backend yet.
  // TODO: confirm the real path (and method) with Ramus.
  static const String _sendPhrasePath = '/api/practice/phrase';

  static const Duration _sendTimeout = Duration(seconds: 15);

  /// Uploads one phrase's worth of detected notes.
  ///
  /// [sessionId] ties every phrase in one recording together on the
  /// backend side. TODO: confirm with Ramus whether the backend expects
  /// this client-generated id as-is, or wants session creation to be its
  /// own request first.
  ///
  /// Fire-and-forget by design: a dropped upload for phrase N shouldn't
  /// block the user from continuing on to phrase N+1, so failures are
  /// logged rather than thrown. Callers don't need to wrap this in
  /// try/catch.
  static Future<void> sendPhrase({
    required String sessionId,
    required int phraseNumber,
    required List<Notes> notes,
  }) async {
    final baseUrl = await ServerDiscovery.resolveBaseUrl();
    if (baseUrl == null) {
      debugPrint(
        '[PhraseUpload] No backend found on network — dropping phrase $phraseNumber.',
      );
      return;
    }

    final body = jsonEncode({
      'session_id': sessionId,
      'phrase': phraseNumber,
      'notes': notes.map(_noteToJson).toList(),
    });

    var response = await _post(baseUrl, body);

    // Same "stale cached address" recovery used elsewhere in the app: a
    // null response means the request itself failed, so re-discover and
    // retry once before giving up on this phrase.
    if (response == null) {
      ServerDiscovery.invalidateCache();
      final freshBaseUrl = await ServerDiscovery.resolveBaseUrl(
        forceRefresh: true,
      );
      if (freshBaseUrl == null) {
        debugPrint(
          '[PhraseUpload] Backend unreachable after retry — dropping phrase $phraseNumber.',
        );
        return;
      }
      response = await _post(freshBaseUrl, body);
    }

    if (response == null) {
      debugPrint(
        '[PhraseUpload] Phrase $phraseNumber failed to send (network error).',
      );
      return;
    }

    if (response.statusCode != 200 &&
        response.statusCode != 201 &&
        response.statusCode != 202) {
      debugPrint(
        '[PhraseUpload] Phrase $phraseNumber rejected: '
        '${response.statusCode} — ${response.body}',
      );
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
  // wiring this up. Replace the placeholder below with the actual
  // pitch/timing/velocity fields once you can see that file — the
  // commented-out lines are a guess at likely field names, not real ones.
  static Map<String, dynamic> _noteToJson(Notes note) {
    return {
      // 'pitch': note.pitch,
      // 'start_ms': note.startMs,
      // 'duration_ms': note.durationMs,
      // 'velocity': note.velocity,
      'raw': note.toString(), // placeholder until real fields are wired in
    };
  }
}