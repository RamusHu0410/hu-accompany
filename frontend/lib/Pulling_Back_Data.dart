import 'package:http/http.dart' as http;
import 'dart:convert'; // Needed to convert data into JSON format

class ApiService {
  // Replace this with your friend's local computer IP address when they return.
  static const String baseUrl = 'http://localhost:8000';

  // This function is 'async' and returns a Promise (Future) of a String (the XML text)
  Future<String> fetchMusicSheet(String songName) async {
    try {
      // 1. Prepare the URL endpoint
      final url = Uri.parse(baseUrl);

      // 2. Prepare the payload body we want to send to Python
      final Map<String, String> requestBody = {
        'sheet_name': songName,
      };

      // 3. Send the POST request and AWAIT the response
      print("Sending request to server for: $songName...");
      final response = await http.post(
        url,
        headers: {
          'Content-Type': 'application/json', // Telling Django we are sending JSON
        },
        body: jsonEncode(requestBody), // Converts the Map into a flat JSON string
      );

      // 4. Check the Status Code sent back by Django
      if (response.statusCode == 200) {
        print("Success! MusicXML received.");
        // The body contains our raw MusicXML string
        return response.body;
      } else if (response.statusCode == 404) {
        throw Exception("Song not found on the server.");
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