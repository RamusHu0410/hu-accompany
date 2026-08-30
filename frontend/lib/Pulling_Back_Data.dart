import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;

import 'ServerDiscovery.dart';

/// Thin client for the PDF-download side of the backend.
///
/// CONFIRMED CONTRACT (from backend logs/responses, not guesswork):
/// POST /api/imslp/download with {"score_id": "..."} does NOT return the
/// PDF directly. It blocks until the backend has found the score on
/// IMSLP, downloaded it, and parsed/stored it under
/// backend/storage/scores/<composer>/<piece>, then returns JSON like:
///   {"status": "completed", "score_id": "345", "file_path": "storage/scores/Beethoven/.../3_Voices_Solo.pdf"}
/// So getting the actual bytes is a TWO-STEP process: this POST, then a
/// second GET for file_path.
class ApiService {
  static const String _downloadPath = '/api/imslp/download';

  // The POST above blocks on the backend actually fetching from IMSLP and
  // parsing — timing varies a lot per piece (one score took ~40s, another
  // timed out past 30s). Generous timeout so slower pieces don't get cut
  // off mid-processing. If pieces regularly take longer than this,
  // bump it further or ask Ramus whether this should become a
  // poll-a-job-status pattern instead of one long blocking request.
  static const Duration _processTimeout = Duration(seconds: 120);

  // The second request just reads a file already sitting on disk — should
  // be fast regardless of how long the first step took.
  static const Duration _fileFetchTimeout = Duration(seconds: 30);

  /// Asks the backend to find/download/parse the PDF for one specific
  /// IMSLP edition (identified by score_id), then fetches the resulting
  /// file's bytes. Returns the raw PDF bytes.
  Future<Uint8List> fetchScorePdf(String scoreId) async {
    final baseUrl = await ServerDiscovery.resolveBaseUrl();
    if (baseUrl == null) {
      throw Exception(
        'Could not find the accompaniment server on this network.',
      );
    }

    var usedBaseUrl = baseUrl;
    var response = await _post(usedBaseUrl, scoreId);

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
      usedBaseUrl = freshBaseUrl;
      response = await _post(usedBaseUrl, scoreId);
      if (response == null) {
        throw Exception('Download failed: server unreachable');
      }
    }

    if (response.statusCode == 404) {
      throw Exception('Piece not found on IMSLP.');
    }
    if (response.statusCode != 200) {
      print(
        'Server rejected request: ${response.statusCode} — ${response.body}',
      );
      throw Exception('Server error code: ${response.statusCode}');
    }

    // Step 1's response is JSON metadata, not the file. Pull file_path out
    // of it and go fetch the actual bytes in step 2.
    final Map<String, dynamic> meta;
    try {
      meta = jsonDecode(response.body) as Map<String, dynamic>;
    } catch (_) {
      throw Exception('Unexpected response from server: ${response.body}');
    }

    final filePath = meta['file_path'] as String?;
    if (filePath == null || filePath.isEmpty) {
      throw Exception('Server response had no file_path: ${response.body}');
    }

    return _fetchFile(usedBaseUrl, filePath);
  }

  /// Step 2: fetches the actual PDF bytes from wherever the backend says
  /// the file landed.
  ///
  /// ASSUMPTION: the backend serves this path directly off the base URL
  /// (e.g. http://Mac.local:8000/storage/scores/...). If Django isn't
  /// exposing /storage/ as a static/media route, this will 404 — worth
  /// confirming with Ramus whether there's a dedicated file-serving
  /// endpoint instead (e.g. /api/imslp/file?path=... ).
  Future<Uint8List> _fetchFile(String baseUrl, String filePath) async {
    final normalizedPath = filePath.startsWith('/') ? filePath : '/$filePath';
    final uri = Uri.parse('$baseUrl$normalizedPath');
    print('Fetching PDF file from: $uri');

    final http.Response response;
    try {
      response = await http.get(uri).timeout(_fileFetchTimeout);
    } on Exception catch (error) {
      throw Exception('Could not fetch PDF file: $error');
    }

    if (response.statusCode != 200) {
      print('File fetch failed: ${response.statusCode} — ${response.body}');
      throw Exception(
        'Could not fetch PDF file: status ${response.statusCode}',
      );
    }

    final bytes = response.bodyBytes;
    // Sanity-check it's actually a PDF (starts with "%PDF") rather than,
    // say, an HTML 404 page served with a 200 status.
    final looksLikePdf =
        bytes.length > 4 &&
        bytes[0] == 0x25 &&
        bytes[1] == 0x50 &&
        bytes[2] == 0x44 &&
        bytes[3] == 0x46; // %PDF
    if (!looksLikePdf) {
      print("Fetched file wasn't a PDF (${bytes.length} bytes).");
      throw Exception('Server did not return a valid PDF file.');
    }

    print('Success! PDF received (${bytes.length} bytes).');
    return bytes;
  }

  /// Returns null on any network-level failure (timeout, socket error,
  /// etc.) so the caller can decide whether to retry against a
  /// re-discovered address — distinct from a clean non-200 HTTP response,
  /// which comes back as a normal Response and is handled by the caller.
  static Future<http.Response?> _post(String baseUrl, String scoreId) async {
    final uri = Uri.parse('$baseUrl$_downloadPath');
    try {
      print('Requesting score PDF for score_id: $scoreId...');
      return await http
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'score_id': scoreId}),
          )
          .timeout(_processTimeout);
    } on Exception {
      return null;
    }
  }
}
