class SearchValidator {
  /// Validates if the query matches the "Artist - Title" format.
  /// Returns null if valid, or a friendly error message if invalid.
  static String? validateQuery(String query) {
    final trimmed = query.trim();

    // Rule 1: Cannot be empty
    if (trimmed.isEmpty) {
      return "Please type something to start searching.";
    }

    // Rule 2: Must contain an explicit delimiter hyphen
    if (!trimmed.contains('-')) {
      return 'Please use the correct format:\n"Artist Name - Song Title"';
    }

    // Split the text into components around the first hyphen
    final parts = trimmed.split('-');
    final artist = parts[0].trim();
    
    // Join the rest back just in case the song title itself contains a hyphen
    final title = parts.sublist(1).join('-').trim();

    // Rule 3: Enforce minimum string lengths on both sides of the hyphen
    if (artist.length < 2) {
      return "The artist name is too short (minimum 2 characters).";
    }

    if (title.length < 3) {
      return "The song title is too vague (minimum 3 characters).";
    }

    // If all guard rails pass, return null (meaning no errors found!)
    return null;
  }
}
