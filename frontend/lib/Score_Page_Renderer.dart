import 'package:flutter/material.dart';

/// One rendered page, plus however many pages the whole piece turned out to
/// need. Total page count usually isn't known until the first page has
/// actually been laid out, which is why it travels alongside the page
/// itself instead of being asked for separately.
class RenderedPage {
  final Widget widget;
  final int totalPages;
  const RenderedPage({required this.widget, required this.totalPages});
}

/// Swap this out once a real MusicXML rendering package is picked. It takes
/// the full score's MusicXML plus the page number you want, and returns
/// that page laid out as a widget (async because real notation layout
/// engines aren't instant).
typedef PageRenderer =
    Future<RenderedPage> Function(String musicXml, int pageNumber);

/// Placeholder renderer so the rest of the app works today. Treats the
/// whole score as a single page — delete this once real rendering is wired
/// in and pass your renderer to ScorePageController instead.
Future<RenderedPage> placeholderPageRenderer(
  String musicXml,
  int pageNumber,
) async {
  return RenderedPage(
    totalPages: 1,
    widget: Center(
      child: Text(
        'Page $pageNumber\n(${musicXml.length} chars of MusicXML)\n\n'
        'TODO: plug your MusicXML renderer in here.',
        textAlign: TextAlign.center,
        style: TextStyle(color: Colors.black.withValues(alpha: 0.4)),
      ),
    ),
  );
}