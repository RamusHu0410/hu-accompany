class SearchValidator {
  /// Validates the search query before it's sent to the server.
  /// Returns null if valid, or a friendly error message if invalid.
  static String? validateQuery(String query) {
    final trimmed = query.trim();

    // Rule: Cannot be empty
    if (trimmed.isEmpty) {
      return "Please type something to start searching.";
    }

    // If all guard rails pass, return null (meaning no errors found!)
    return null;
  }
}