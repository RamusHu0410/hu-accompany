import 'dart:convert';

import 'package:http/http.dart' as http;

import 'package:hu_accomponist/integrations/scores/score_models.dart';
import 'package:hu_accomponist/integrations/server/ServerDiscovery.dart';

/// Loads scores from the backend's /api/scores endpoints.
///
/// The address is discovered over mDNS. A network-level failure (not an
/// HTTP error) usually means the cached address went stale, so each call
/// re-discovers and retries once before giving up.
class ScoreRepository {
  const ScoreRepository();

  static const Duration _timeout = Duration(seconds: 15);

  /// Scores whose title or composer contain every word of [query].
  Future<List<ScoreSummary>> search(String query) async {
    final response = await _get('/api/scores/search', {'q': query});
    if (response.statusCode != 200) {
      throw Exception('Search failed (status ${response.statusCode}).');
    }
    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    final results = decoded['results'] as List<dynamic>? ?? const [];
    return [
      for (final raw in results)
        ScoreSummary.fromJson(raw as Map<String, dynamic>),
    ];
  }

  /// Fetches the MusicXML for [score].
  Future<LoadedScore> load(ScoreSummary score) async {
    final response = await _get('/api/scores/${score.id}/musicxml');
    if (response.statusCode == 404) {
      throw Exception('That score is no longer available.');
    }
    if (response.statusCode != 200) {
      throw Exception('Could not load score (status ${response.statusCode}).');
    }
    return LoadedScore(
      summary: score,
      musicXml: utf8.decode(response.bodyBytes),
    );
  }

  Future<http.Response> _get(String path, [Map<String, String>? query]) async {
    final first = await _attempt(path, query, forceRefresh: false);
    if (first != null) return first;

    ServerDiscovery.invalidateCache();
    final second = await _attempt(path, query, forceRefresh: true);
    if (second != null) return second;
    throw Exception('Could not reach the accompaniment server.');
  }

  /// Null on a network-level failure, so [_get] can retry.
  Future<http.Response?> _attempt(
    String path,
    Map<String, String>? query, {
    required bool forceRefresh,
  }) async {
    final baseUrl = await ServerDiscovery.resolveBaseUrl(
      forceRefresh: forceRefresh,
    );
    if (baseUrl == null) {
      throw Exception(
        'Could not find the accompaniment server on this network.',
      );
    }
    final uri = Uri.parse('$baseUrl$path').replace(queryParameters: query);
    try {
      return await http.get(uri).timeout(_timeout);
    } on Exception {
      return null;
    }
  }
}
