import 'package:http/http.dart' as http;
import 'dart:convert'; // Needed to convert data into JSON format
import 'dart:typed_data';

class ApiService {
  // Replace this with your friend's local computer IP address when they return.
  static const String baseUrl = 'http://172.28.178.9:8000';

  /// Asks the backend to look up [pieceName] on IMSLP. If found, the
  /// backend downloads and parses the PDF and stores it under
  /// backend/storage/scores/<composer>/<piece_name>, then returns the raw
  /// PDF bytes in the response body.
  ///
  /// NOTE: this used to return a MusicXML string (see fetchMusicSheet,
  /// now removed). The backend no longer produces MusicXML for this flow —
  /// it's a literal PDF now, so the return type changed from String to
  /// Uint8List. Whatever renders this on the Flutter side needs to be a
  /// PDF viewer, not the OSMD WebView.
  Future<Uint8List> fetchScorePdf(String scoreId, String imslpUrl) async {
    try {
      // 1. Prepare the URL endpoint
      final url = Uri.parse('$baseUrl/api/imslp/download');

      // 2. Prepare the payload body we want to send to Django.
      //    Matches the contract read by imslp_downloader/api.py: score_id
      //    and imslp_url.
      final Map<String, String> requestBody = {
        'score_id': scoreId,
        'imslp_url': imslpUrl,
      };

      // 3. Send the POST request and AWAIT the response
      print("Requesting score PDF for: $scoreId ($imslpUrl)...");
      final response = await http.post(
        url,
        headers: {
          'Content-Type': 'application/json', // Telling Django we are sending JSON
        },
        body: jsonEncode(requestBody), // Converts the Map into a flat JSON string
      );

      // 4. Check the Status Code sent back by Django
      if (response.statusCode == 200) {
        print("Success! PDF received (${response.bodyBytes.length} bytes).");
        // The body is now raw PDF bytes, not a MusicXML string.
        return response.bodyBytes;
      } else if (response.statusCode == 404) {
        throw Exception("Piece not found on IMSLP.");
      } else {
        throw Exception("Server error code: ${response.statusCode}");
      }
    } catch (error) {
      // Catches network errors (like no internet connection or server offline)
      print("Network error occurred: $error");
      throw Exception("Could not connect to the server.");
    }
  }
}