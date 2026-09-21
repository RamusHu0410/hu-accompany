import 'package:flutter/material.dart';

import 'package:hu_accomponist/features/search/Music_Library_Page.dart';
import 'package:hu_accomponist/features/shelf/Shelf_Manager.dart';
import 'package:hu_accomponist/integrations/scores/Pulling_Back_Data.dart';
import 'package:hu_accomponist/main.dart' show ScoreViewerPage;
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// Opening a score for practice, from wherever it was chosen.
///
/// Both the library and the shelf need to land the user on the score, and
/// previously neither did: the library popped a [SelectedSheet] that only
/// the practice screen knew how to consume, so choosing a sheet from the
/// turntable dropped the user back at home, and the shelf only showed a
/// snackbar. Keeping the transition in one place means a new entry point
/// gets the same behaviour for free.
abstract final class OpenPractice {
  /// Replaces the current route with the score viewer.
  ///
  /// `pushReplacement` rather than `push` so Back from the score returns to
  /// the turntable rather than to the picker the user already finished with.
  static Future<void> withSheet(
    BuildContext context,
    SelectedSheet selected,
  ) {
    return Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) => ScoreViewerPage(selected: selected),
      ),
    );
  }

  /// Opens a score the user previously played, from the shelf.
  ///
  /// The shelf stores only id/title/composer, so the PDF has to be fetched
  /// before the viewer can show anything. That is a network round trip, so
  /// the caller gets a blocking progress dialog rather than an unexplained
  /// pause on a tapped tile.
  static Future<void> withShelfEntry(
    BuildContext context,
    ShelfEntry entry,
  ) async {
    final navigator = Navigator.of(context);
    final messenger = ScaffoldMessenger.of(context);

    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(
        child: CircularProgressIndicator(strokeWidth: 2.5),
      ),
    );

    try {
      final pdfBytes = await ApiService().fetchScorePdf(entry.id);
      // Dismiss the progress dialog before routing onward.
      navigator.pop();
      await navigator.pushReplacement(
        MaterialPageRoute(
          builder: (_) => ScoreViewerPage(
            selected: SelectedSheet(
              sheet: MusicSheet(
                id: entry.id,
                title: entry.title,
                // The shelf never recorded the source URL, and nothing
                // downstream reads it — the bytes are already in hand.
                pdfUrl: '',
              ),
              pdfBytes: pdfBytes,
              composer: entry.composer,
            ),
          ),
        ),
      );
    } catch (e) {
      navigator.pop();
      messenger.showSnackBar(
        SnackBar(
          content: Text(_friendly(e)),
          duration: const Duration(seconds: 4),
          behavior: SnackBarBehavior.floating,
          margin: const EdgeInsets.all(Space.md),
        ),
      );
    }
  }

  /// Strips Dart's "Exception: " prefix so a backend reason reads naturally.
  static String _friendly(Object e) {
    final message = e.toString();
    return message.startsWith('Exception: ')
        ? message.substring(11)
        : message;
  }
}
