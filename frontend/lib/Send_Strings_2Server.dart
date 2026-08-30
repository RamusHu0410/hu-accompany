import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'Music_Library_Page.dart' show MusicSheet;
import 'ServerDiscovery.dart';

/// One entry in a composer's work list — just enough to display a row
/// and let the user drill in. Does NOT carry edition/arrangement info;
/// that's fetched separately (see [MusicSheetService.fetchWorkEditions])
/// once the user actually taps into a specific piece.
class WorkSummary {
  final String title;
  final String composer;
  final String url;

  const WorkSummary({
    required this.title,
    required this.composer,
    required this.url,
  });
}

/// Thin client for talking to your friend's Django backend. Address is
/// discovered via mDNS/Bonjour (see ServerDiscovery.dart) rather than
/// hardcoded, since dev machines move between networks/DHCP leases.
class MusicSheetService {
  MusicSheetService._();

  // imslp_search_view — the backend decides, per query, whether it looks
  // like a composer name or a specific work title, and replies with one
  // of two different shapes:
  //
  //   Composer match:
  //   { "composer": "Chopin, Frédéric", "works": [ {title, composer, url}, ... ] }
  //
  //   Specific-work match:
  //   { "title": "...", "composer": "...", "imslp_url": "...",
  //     "choices": [ {id, name, instrumentation, type, imslp_url,
  //                   movement, arranger, editor, file_name}, ... ] }
  static const String _searchPath = '/api/imslp/search';

  static const Duration _searchTimeout = Duration(seconds: 10);

  /// Top-level search box entry point. Always returns a flat list of
  /// [WorkSummary] — one per matching piece — regardless of which shape
  /// the backend replied with, so the library page never has to care
  /// which case it got.
  static Future<List<WorkSummary>> searchMusic(String query) async {
    final decoded = await _postSearch(query);
    if (decoded == null) return [];

    // Composer match: a real list of works.
    if (decoded.containsKey('works')) {
      final fallbackComposer = decoded['composer'] as String? ?? '';
      final List<dynamic> works = decoded['works'] as List<dynamic>? ?? [];
      return works.map((raw) {
        final map = raw as Map<String, dynamic>;
        return WorkSummary(
          title: map['title'] as String? ?? 'Untitled',
          composer: (map['composer'] as String?) ?? fallbackComposer,
          url: map['url'] as String? ?? '',
        );
      }).toList();
    }

    // Specific-work match: the query already landed on one piece. Wrap it
    // as a single-item list so the caller's code path stays uniform —
    // tapping it will re-fetch (via fetchWorkEditions) to get its actual
    // editions/arrangements, same as any other row.
    if (decoded.containsKey('choices')) {
      return [
        WorkSummary(
          title: decoded['title'] as String? ?? 'Untitled',
          composer: decoded['composer'] as String? ?? '',
          url: decoded['imslp_url'] as String? ?? '',
        ),
      ];
    }

    return [];
  }

  /// Fetches every edition/arrangement/version of one specific work by
  /// title — this is what turns a tapped row into the actual list of
  /// versions to choose from (or, if there's only one, the sheet to
  /// open directly).
  ///
  /// Re-hits the same endpoint the composer search used, but with the
  /// exact work title as the query, which is what triggers the backend's
  /// specific-work ("choices") response shape.
  static Future<List<MusicSheet>> fetchWorkEditions(String workTitle) async {
    final decoded = await _postSearch(workTitle);
    if (decoded == null) return [];

    final resolvedTitle = decoded['title'] as String? ?? workTitle;
    final composer = decoded['composer'] as String? ?? '';
    final List<dynamic> choices = decoded['choices'] as List<dynamic>? ?? [];

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
      final descriptor = details.isEmpty
          ? name
          : '$name (${details.join(', ')})';

      final title = composer.isEmpty
          ? '$resolvedTitle — $descriptor'
          : '$resolvedTitle — $composer — $descriptor';

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

  /// Shared discovery + POST + status-code handling for both entry points
  /// above. Resolves the backend address via mDNS, posts the query, and
  /// — if the request itself fails (not a 404, an actual network
  /// failure) — assumes the cached address went stale (e.g. the backend
  /// restarted with a new IP) and retries once against a freshly
  /// re-discovered address before giving up.
  ///
  /// Returns null for a 404 ("no match" — not an error), throws for any
  /// other failure (including "couldn't find the server at all").
  static Future<Map<String, dynamic>?> _postSearch(String query) async {
    final baseUrl = await ServerDiscovery.resolveBaseUrl();
    if (baseUrl == null) {
      throw Exception(
        'Could not find the accompaniment server on this network.',
      );
    }

    var response = await _post(baseUrl, query);

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
      response = await _post(freshBaseUrl, query);
      if (response == null) {
        throw Exception('Search failed: server unreachable');
      }
    }

    // 404 here means imslp_service.search() raised WorkNotFoundError —
    // that's a legitimate "nothing matched," not a failure.
    if (response.statusCode == 404) {
      return null;
    }

    if (response.statusCode != 200) {
      throw Exception('Search failed with status ${response.statusCode}');
    }

    final decoded = jsonDecode(response.body) as Map<String, dynamic>;
    debugPrint('search raw keys: ${decoded.keys.toList()}');
    return decoded;
  }

  /// Returns null on any network-level failure (timeout, socket error,
  /// etc.) so the caller can decide whether to retry against a
  /// re-discovered address — distinct from a clean non-200 HTTP response,
  /// which comes back as a normal Response and is handled by the caller.
  static Future<http.Response?> _post(String baseUrl, String query) async {
    final uri = Uri.parse('$baseUrl$_searchPath');
    try {
      return await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'query': query}),
          )
          .timeout(_searchTimeout);
    } on Exception {
      return null;
    }
  }
}
