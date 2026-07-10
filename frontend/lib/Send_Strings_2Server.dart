import 'dart:convert';
import 'package:http/http.dart' as http;

import 'Music_Library_Page.dart' show MusicSheet;

/// Thin client for talking to your friend's Django backend.
///
/// TODO: confirm these three things with your friend, then update below:
///   1. baseUrl
///   2. the exact search endpoint + whether it's GET ?q= or a POST body
///   3. the exact JSON keys coming back for search results and for the score
class MusicSheetService {
  MusicSheetService._();

  // TODO: point this at the real server.
  static const String baseUrl = 'http://localhost:8000';

  static const String _searchPath = '/api/search/';

  static const Duration _searchTimeout = Duration(seconds: 10);

  /// Sends the already-validated "Artist - Title" query to Django and
  /// returns the matching sheets (metadata only — no MusicXML yet).
  ///
  /// Throws on a network error or non-200 response so the caller's
  /// try/catch can surface a friendly error message.
  static Future<List<MusicSheet>> searchMusic(String query) async {
    final uri = Uri.parse(
      '$baseUrl$_searchPath',
    ).replace(queryParameters: {'q': query});

    final response = await http.get(uri).timeout(_searchTimeout);

    if (response.statusCode != 200) {
      throw Exception('Search failed with status ${response.statusCode}');
    }

    final decoded = jsonDecode(response.body);

    // TODO: adjust if the payload is wrapped, e.g. {"results": [...]}
    final List<dynamic> rawList = decoded as List<dynamic>;

    return rawList.map((raw) {
      final map = raw as Map<String, dynamic>;
      return MusicSheet(
        // TODO: swap these keys for whatever your friend's serializer uses.
        id: map['id'].toString(),
        title: map['title'] as String? ?? 'Untitled',
        thumbnailUrl: map['thumbnail_url'] as String?,
        pdfUrl: map['pdf_url'] as String? ?? '',
      );
    }).toList();
  }

}