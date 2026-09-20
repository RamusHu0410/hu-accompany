import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../models/Quiz_Set.dart';
import 'ServerDiscovery.dart';

/// Thin client for the backend's quiz package (backend/quiz).
///
/// Follows the same shape as MusicSheetService: the address is discovered
/// over mDNS rather than hardcoded, and a network-level failure retries
/// once against a freshly discovered address before giving up, since dev
/// machines move between networks.
class QuizGenerator {
  QuizGenerator._();

  static const String _generatePath = '/api/quiz/generate';

  /// Generation is pure CPU on the server — no scraping, no model call — so
  /// this can be far tighter than the IMSLP search timeout.
  static const Duration _timeout = Duration(seconds: 8);

  /// Builds a quiz for a typed topic heading, e.g.
  ///
  ///     RCM HISTORY 10 + ARCT CHEAT SHEET
  ///     The Middle Ages (ad 476 - ad 1450)
  ///
  /// [length] is clamped server-side to 5-60. [seed] makes the draw
  /// reproducible and is only used by tests.
  ///
  /// Throws with a message suitable for showing the user: the backend's own
  /// reason where it sent one (an unknown era lists the eras it does cover),
  /// otherwise a network failure.
  static Future<QuizSet> generate(
    String topic, {
    int length = 15,
    int? seed,
  }) async {
    final body = <String, dynamic>{
      'topic': topic,
      'length': length,
      if (seed != null) 'seed': seed,
    };

    final baseUrl = await ServerDiscovery.resolveBaseUrl();
    if (baseUrl == null) {
      throw Exception(
        'Could not find the accompaniment server on this network.',
      );
    }

    var response = await _post(baseUrl, body);

    if (response == null) {
      ServerDiscovery.invalidateCache();
      final freshBaseUrl = await ServerDiscovery.resolveBaseUrl(
        forceRefresh: true,
      );
      if (freshBaseUrl == null) {
        throw Exception(
          'Could not find the accompaniment server on this network.',
        );
      }
      response = await _post(freshBaseUrl, body);
      if (response == null) {
        throw Exception('Quiz generation failed: server unreachable');
      }
    }

    if (response.statusCode != 200) {
      throw Exception(_errorFrom(response));
    }

    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final set = QuizSet.fromJson(decoded);
    if (set.isEmpty) {
      throw Exception('That topic produced no questions.');
    }
    return set;
  }

  /// Surfaces the backend's own `error` string where there is one — a 404
  /// carries the list of eras that do have banks, which is far more useful
  /// than "request failed". Falls back to the status code.
  static String _errorFrom(http.Response response) {
    try {
      final decoded = jsonDecode(response.body) as Map<String, dynamic>;
      final message = decoded['error'] as String?;
      if (message != null && message.isNotEmpty) return message;
    } on FormatException {
      // Body was not JSON — fall through to the status code.
    }
    return 'Quiz generation failed with status ${response.statusCode}';
  }

  /// Returns null on a network-level failure so the caller can retry
  /// against a re-discovered address, matching MusicSheetService._post.
  static Future<http.Response?> _post(
    String baseUrl,
    Map<String, dynamic> body,
  ) async {
    final uri = Uri.parse('$baseUrl$_generatePath');
    try {
      return await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(body),
          )
          .timeout(_timeout);
    } catch (e) {
      debugPrint('QuizGenerator: POST $uri failed — $e');
      return null;
    }
  }
}
