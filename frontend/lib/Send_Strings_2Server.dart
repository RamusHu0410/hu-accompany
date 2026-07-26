import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'Music_Library_Page.dart' show MusicSheet;

/// Thin client for talking to your friend's Django backend.
class MusicSheetService {
  MusicSheetService._();

  static const String baseUrl = 'http://172.28.178.10:8000';

  // imslp_search_view — returns a single matched Work with its available
  // editions/arrangements nested under "choices", NOT a flat list of
  // different pieces under a "results" key like the old search_view did.
  static const String _searchPath = '/api/imslp/search';

  static const Duration _searchTimeout = Duration(seconds: 10);

  /// Sends the query to Django's /api/imslp/search and returns one
  /// selectable MusicSheet per edition/arrangement of the matched work.
  ///
  /// Example response shape this parses:
  /// {
  ///   "title": "3 Nouvelles études, B.130",
  ///   "composer": "Chopin, Frédéric",
  ///   "imslp_url": "https://imslp.org/wiki/...",
  ///   "choices": [
  ///     {
  ///       "id": "228",
  ///       "name": "Piano Solo",
  ///       "instrumentation": "Piano",
  ///       "type": "Original Score",
  ///       "imslp_url": "https://imslp.org/wiki/Special:ImagefromIndex/399450",
  ///       "movement": null,
  ///       "arranger": null,
  ///       "editor": null,
  ///       "file_name": "PMLP02634-BnF_btv1b52500458h.pdf"
  ///     },
  ///     ...
  ///   ]
  /// }
  ///
  /// Throws on a network error or non-200 (other than 404, which means
  /// "no matching work" and just yields an empty result list rather than
  /// an error). Callers should still try/catch for real failures.
  static Future<List<MusicSheet>> searchMusic(String query) async {
    final uri = Uri.parse('$baseUrl$_searchPath');

    final response = await http
        .post(
          uri,
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'query': query}),
        )
        .timeout(_searchTimeout);

    // 404 here means imslp_service.search() raised WorkNotFoundError —
    // that's a legitimate "nothing matched," not a failure, so we return
    // an empty list instead of throwing (which would surface as a scary
    // "Network connection failed" for what's really just "no results").
    if (response.statusCode == 404) {
      return [];
    }

    if (response.statusCode != 200) {
      throw Exception('Search failed with status ${response.statusCode}');
    }

    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    // TEMP DEBUG — remove once the imslp response shape is confirmed.
    debugPrint('searchMusic raw keys: ${decoded.keys.toList()}');
    debugPrint('searchMusic raw body: ${response.body}');

    final workTitle = decoded['title'] as String? ?? 'Untitled';
    final composer = decoded['composer'] as String? ?? '';
    final List<dynamic> choices = decoded['choices'] as List<dynamic>? ?? [];
    debugPrint('searchMusic parsed choices.length: ${choices.length}');

    return choices.map((raw) {
      final map = raw as Map<String, dynamic>;

      final id = map['id']?.toString() ?? '';
      final name = map['name'] as String? ?? 'Version';
      final movement = map['movement'] as String?;
      final arranger = map['arranger'] as String?;
      final editor = map['editor'] as String?;
      // Per-choice imslp_url points at the actual score page for that
      // specific edition — that's the one to open, not the top-level
      // work imslp_url (which is just the work's general wiki page).
      final url = map['imslp_url'] as String? ?? '';

      // Build a short descriptor from whichever optional fields exist,
      // e.g. "Piano Solo (Selections, ed. Romain Behar)".
      final details = <String>[
        if (movement != null && movement.isNotEmpty) movement,
        if (arranger != null && arranger.isNotEmpty) 'arr. $arranger',
        if (editor != null && editor.isNotEmpty) 'ed. $editor',
      ];
      final descriptor =
          details.isEmpty ? name : '$name (${details.join(', ')})';

      final title = composer.isEmpty
          ? '$workTitle — $descriptor'
          : '$workTitle — $composer — $descriptor';

      return MusicSheet(
        // Prefer the numeric choice id (unique per edition); fall back to
        // the URL only if id is somehow missing.
        id: id.isEmpty ? url : id,
        title: title,
        thumbnailUrl: null,
        pdfUrl: url,
      );
    }).toList();
  }
}