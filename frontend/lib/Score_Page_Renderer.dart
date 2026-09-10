import 'dart:async';
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

/// Owns one PDF document for one score viewer.
///
/// The old implementation used a process-wide document cache. When a new
/// score opened, it closed that shared document while old page futures were
/// still rendering. It also let pdfx render multiple pages concurrently.
/// Both behaviors caused swapped pages and PdfDocumentAlreadyClosedException.
class PdfScoreDocument {
  final Uint8List bytes;
  pdfx.PdfDocument? _document;
  Future<void> _queue = Future<void>.value();
  bool _disposed = false;

  PdfScoreDocument(this.bytes);

  Future<pdfx.PdfDocument> _open() async {
    return _document ??= await pdfx.PdfDocument.openData(bytes);
  }

  Future<RenderedPage> renderPage(Uint8List ignoredBytes, int pageNumber) {
    final completer = Completer<RenderedPage>();

    _queue = _queue
        .then((_) async {
          if (_disposed) {
            throw StateError('PDF document session has been disposed');
          }

          final doc = await _open();
          if (pageNumber < 1 || pageNumber > doc.pagesCount) {
            throw RangeError.range(pageNumber, 1, doc.pagesCount);
          }

          debugPrint(
            'PDF render: bytes=${bytes.length}, pages=${doc.pagesCount}, '
            'requested=$pageNumber',
          );

          final page = await doc.getPage(pageNumber);
          try {
            final image = await page.render(
              width: page.width * 2,
              height: page.height * 2,
              format: pdfx.PdfPageImageFormat.png,
            );
            if (image == null) {
              throw Exception('pdfx failed to render page $pageNumber');
            }
            completer.complete(
              RenderedPage(
                totalPages: doc.pagesCount,
                widget: Image.memory(
                  image.bytes,
                  width: double.infinity,
                  fit: BoxFit.fitWidth,
                ),
              ),
            );
          } finally {
            await page.close();
          }
        })
        .catchError((Object error, StackTrace stack) {
          if (!completer.isCompleted) completer.completeError(error, stack);
        });

    // Keep the queue alive after a failed page so later pages can still try.
    _queue = _queue.catchError((_) {});
    return completer.future;
  }

  Future<void> dispose() {
    _disposed = true;
    final close = _queue.then((_) async {
      await _document?.close();
      _document = null;
    });
    _queue = close.catchError((_) {});
    return close;
  }
}

/// Renders one PDF page to an image widget. Pass this (or just rely on the
/// default) as the `render` argument to [ScorePageController].
Future<RenderedPage> pdfPageRenderer(Uint8List pdfBytes, int pageNumber) async {
  // Standalone callers get an isolated, serialized document session. The
  // ScorePageController uses its own session and disposes it with the view.
  final session = PdfScoreDocument(pdfBytes);
  try {
    return await session.renderPage(pdfBytes, pageNumber);
  } finally {
    await session.dispose();
  }
}
