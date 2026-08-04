import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;

import 'ServerDiscovery.dart';

/// Thin client for the PDF-download side of the backend. Mirrors the
/// discovery/retry pattern MusicSheetService (Send_Strings_2Server.dart)
/// already uses for search — resolves the backend address via mDNS
/// instead of a hardcoded IP, since dev machines move between
/// networks/DHCP leases.
///
/// CHANGED: this used to hardcode `baseUrl = 'http://172.28.176.30:8000'`
/// with a comment telling you to manually update the IP. That's what was
/// causing "Host is down" / "Operation timed out" — the search calls
/// worked because they already went through ServerDiscovery, but this
/// file was still on the stale manual IP. Now it goes through the same
/// discovery path.
class ApiService {
  static const String _downloadPath = '/api/imslp/download';

  // Longer than the search timeout — this involves the backend actually
  // fetching a PDF from IMSLP and parsing it, not just a DB/local lookup.
  static const Duration _downloadTimeout = Duration(seconds: 30);

  /// Asks the backend to download and parse the PDF for one specific
  /// IMSLP edition, identified by score_id (the numeric/string id the
  /// backend already returned per-choice from /api/imslp/search — see
  /// MusicSheet.id in Music_Library_Page.dart). If found, the backend
  /// stores it under backend/storage/scores/<composer>/<piece_name> and
  /// returns the raw PDF bytes in the response body.
  ///
  /// CONFIRMED via backend error: {"error": "score_id is required"} —
  /// this used to send imslp_url under a 'url' field, which the backend
  /// rejected. Field name and value are now known-correct, not guesses.
  Future<Uint8List> fetchScorePdf(String scoreId) async {
    final baseUrl = await ServerDiscovery.resolveBaseUrl();
    if (baseUrl == null) {
      throw Exception(
        'Could not find the accompaniment server on this network.',
      );
    }

    var response = await _post(baseUrl, scoreId);

    // Same "stale cached address" recovery as MusicSheetService: a null
    // response here means the request itself failed (not a clean HTTP
    // error), so re-discover and retry once before giving up.
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
      response = await _post(freshBaseUrl, scoreId);
      if (response == null) {
        throw Exception('Download failed: server unreachable');
      }
    }

    if (response.statusCode == 200) {
      final bytes = response.bodyBytes;
      // A real PDF always starts with the 4 bytes "%PDF". If it doesn't,
      // the backend returned something else on a 200 — e.g. a small JSON
      // status/job response — rather than the actual file. Catch that
      // here with a clear error instead of silently handing bogus bytes
      // to pdfx, where it fails in a way that looks like "stuck loading"
      // rather than an actual error (see Score_Pages_View fix).
      final looksLikePdf = bytes.length > 4 &&
          bytes[0] == 0x25 &&
          bytes[1] == 0x50 &&
          bytes[2] == 0x44 &&
          bytes[3] == 0x46; // %PDF
      if (!looksLikePdf) {
        print(
          "200 response wasn't a PDF (${bytes.length} bytes). Body: ${response.body}",
        );
        throw Exception(
          "Server returned success but not a PDF: ${response.body}",
        );
      }
      print("Success! PDF received (${bytes.length} bytes).");
      return bytes;
    } else if (response.statusCode == 404) {
      throw Exception("Piece not found on IMSLP.");
    } else {
      // Print the actual backend error message rather than just the
      // status code — the fastest way to nail down the real field
      // name/shape it expects if this still isn't right.
      print(
        "Server rejected request: ${response.statusCode} — ${response.body}",
      );
      throw Exception("Server error code: ${response.statusCode}");
    }
  }

  /// Returns null on any network-level failure (timeout, socket error,
  /// etc.) so the caller can decide whether to retry against a
  /// re-discovered address — distinct from a clean non-200 HTTP response,
  /// which comes back as a normal Response and is handled by the caller.
  static Future<http.Response?> _post(String baseUrl, String scoreId) async {
    final uri = Uri.parse('$baseUrl$_downloadPath');
    try {
      print("Requesting score PDF for score_id: $scoreId...");
      return await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'score_id': scoreId}),
          )
          .timeout(_downloadTimeout);
    } on Exception {
      return null;
    }
  }
}