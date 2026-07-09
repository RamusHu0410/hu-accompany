import 'Score_Page_Renderer.dart';
import 'package:flutter/material.dart';

/// Lays out one score's pages on demand from its already-fetched MusicXML,
/// and keeps a page ahead pre-rendered so turning the page feels instant
/// instead of triggering a visible layout pause.
class ScorePageController {
  final String musicXml;
  final PageRenderer render;

  ScorePageController(this.musicXml, {this.render = placeholderPageRenderer});

  final Map<int, Future<RenderedPage>> _pages = {};

  // Null until page 1 has been rendered — that's what tells us how many
  // pages the piece actually needs.
  int? totalPages;

  Future<RenderedPage> getPage(int pageNumber) {
    return _pages.putIfAbsent(pageNumber, () async {
      final result = await render(musicXml, pageNumber);
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