import 'dart:typed_data';
import 'Score_Page_Renderer.dart';

/// Lays out one score's pages on demand from its already-fetched PDF bytes,
/// and keeps a page ahead pre-rendered so turning the page feels instant
/// instead of triggering a visible layout pause.
///
/// CHANGED: this used to take `musicXml` (a String) since the backend
/// returned MusicXML. It now returns a literal PDF, so this takes the raw
/// PDF bytes instead and defaults to [pdfPageRenderer].
class ScorePageController {
  final Uint8List pdfBytes;
  final PageRenderer render;

  ScorePageController(this.pdfBytes, {this.render = pdfPageRenderer});

  final Map<int, Future<RenderedPage>> _pages = {};

  // Null until page 1 has been rendered — that's what tells us how many
  // pages the piece actually needs.
  int? totalPages;

  Future<RenderedPage> getPage(int pageNumber) {
    return _pages.putIfAbsent(pageNumber, () async {
      final result = await render(pdfBytes, pageNumber);
      totalPages ??= result.totalPages;
      return result;
    });
  }

  /// Loads [pageNumber] and, if there's a next page, silently starts
  /// rendering it too. A failed prefetch is swallowed and the slot cleared
  /// so a real request can retry later — the user hasn't asked for that
  /// page yet.
  Future<RenderedPage> warmPage(int pageNumber) {
    final current = getPage(pageNumber);

    final next = pageNumber + 1;
    if (totalPages == null || next <= totalPages!) {
      getPage(next).catchError((_) {
        _pages.remove(next);
        return RenderedPage(totalPages: totalPages ?? 1, widget: const SizedBox());
      });
    }

    return current;
  }
}