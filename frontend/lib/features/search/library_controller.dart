import 'package:flutter/foundation.dart';

import 'package:hu_accomponist/features/search/Library_Browse.dart';
import 'package:hu_accomponist/features/search/Search_Validator.dart';
import 'package:hu_accomponist/features/shelf/Shelf_Manager.dart';
import 'package:hu_accomponist/integrations/scores/score_models.dart';
import 'package:hu_accomponist/integrations/scores/score_repository.dart';

/// Search and open state for the music library page. The page only renders
/// what this exposes and forwards taps back to it.
class LibraryController extends ChangeNotifier {
  LibraryController({ScoreRepository repository = const ScoreRepository()})
    : _repository = repository;

  final ScoreRepository _repository;

  List<ScoreSummary> results = const [];
  bool hasSearched = false;
  bool isLoading = false;
  String? errorMessage;

  /// True while the page shows its browsable front matter rather than the
  /// outcome of a search.
  bool get isBrowsing => !hasSearched && !isLoading && errorMessage == null;

  Future<void> search(String query) async {
    final validationError = SearchValidator.validateQuery(query);
    if (validationError != null) {
      errorMessage = validationError;
      results = const [];
      notifyListeners();
      return;
    }

    isLoading = true;
    errorMessage = null;
    notifyListeners();
    try {
      results = await _repository.search(query.trim());
      hasSearched = true;
    } catch (e) {
      debugPrint('ScoreRepository.search failed: $e');
      errorMessage = 'Network connection failed.';
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  void reset() {
    results = const [];
    hasSearched = false;
    errorMessage = null;
    notifyListeners();
  }

  /// Fetches [score]'s MusicXML and records it as played. Null on failure,
  /// with the reason in [errorMessage].
  Future<LoadedScore?> open(ScoreSummary score) async {
    LibraryShelfStore.remember(
      LibraryPick(title: score.title, composer: score.composer),
    );
    isLoading = true;
    errorMessage = null;
    notifyListeners();
    try {
      final loaded = await _repository.load(score);
      ShelfManager.recordPlay(
        id: score.id,
        title: score.title,
        composer: score.composer,
      );
      return loaded;
    } catch (e) {
      errorMessage = friendlyError(e);
      return null;
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  /// Strips Dart's "Exception: " prefix so a backend reason reads naturally.
  static String friendlyError(Object e) {
    final message = e.toString();
    return message.startsWith('Exception: ') ? message.substring(11) : message;
  }
}
