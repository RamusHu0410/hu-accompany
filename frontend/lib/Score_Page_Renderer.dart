import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:pdfx/pdfx.dart' as pdfx;

// NOTE: this file didn't exist in what was uploaded — Score_Page_Controller
// imported it but its contents weren't shared, so this is a fresh
// implementation built to match the interface Score_Page_Controller.dart
// already expects (RenderedPage with totalPages+widget, a PageRenderer
// typedef, a default renderer function). If your real
// Score_Page_Renderer.dart looked different, replace this with your
// version and just keep the PDF-specific bits below.
//
// Requires the `pdfx` package — add to pubspec.yaml:
//   pdfx: ^2.6.0

/// One already-rendered page, plus how many pages the whole document has
/// (only known for certain once page 1 has actually been rendered).
class RenderedPage {
  final int totalPages;
  final Widget widget;
  const RenderedPage({required this.totalPages, required this.widget});
}

/// Renders page [pageNumber] (1-indexed) of [pdfBytes] into a displayable
/// widget, returning the page count alongside it.
typedef PageRenderer =
    Future<RenderedPage> Function(Uint8List pdfBytes, int pageNumber);

// Keeps the last-opened pdfx.PdfDocument around so swiping through pages
// of the SAME score doesn't re-parse the whole PDF from bytes on every
// single page turn — ScorePageController calls this renderer once per
// page, not once per score. Keyed by identity (same Uint8List instance)
// rather than content, which is fine since a new ScorePageController (and
// therefore a fresh Uint8List) is created per score in main.dart.
Uint8List? _cachedBytes;
pdfx.PdfDocument? _cachedDoc;

Future<pdfx.PdfDocument> _openCached(Uint8List pdfBytes) async {
  if (identical(_cachedBytes, pdfBytes) && _cachedDoc != null) {
    return _cachedDoc!;
  }
  // A different score was loaded — close the old document first so we
  // don't leak native pdfium resources.
  await _cachedDoc?.close();
  final doc = await pdfx.PdfDocument.openData(pdfBytes);
  _cachedBytes = pdfBytes;
  _cachedDoc = doc;
  return doc;
}

/// Renders one PDF page to an image widget. Pass this (or just rely on the
/// default) as the `render` argument to [ScorePageController].
Future<RenderedPage> pdfPageRenderer(Uint8List pdfBytes, int pageNumber) async {
  final doc = await _openCached(pdfBytes);
  final page = await doc.getPage(pageNumber);
  try {
    // Rendering at 2x the page's own point size gives a reasonably crisp
    // result on high-DPI screens without ballooning memory/time on very
    // large scores. Bump this if pages look soft, or drop it if loading
    // feels slow on bigger scores.
    final image = await page.render(
      width: page.width * 2,
      height: page.height * 2,
      format: pdfx.PdfPageImageFormat.png,
    );
    if (image == null) {
      throw Exception('pdfx failed to render page $pageNumber');
    }
    return RenderedPage(
      totalPages: doc.pagesCount,
      widget: Image.memory(image.bytes, fit: BoxFit.contain),
    );
  } finally {
    await page.close();
  }
}
