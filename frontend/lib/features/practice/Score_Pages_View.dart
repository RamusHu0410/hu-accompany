import 'package:flutter/material.dart';
import 'package:hu_accomponist/features/practice/Score_Page_Controller.dart';
import 'package:hu_accomponist/features/practice/Score_Page_Renderer.dart';

/// Vertically scrollable score pages. Each page fills the score area's width,
/// making music readable on phones without covering the app controls.
class Score_Pages_View extends StatefulWidget {
  final ScorePageController controller;

  const Score_Pages_View({super.key, required this.controller});

  @override
  State<Score_Pages_View> createState() => _Score_Pages_ViewState();
}

class _Score_Pages_ViewState extends State<Score_Pages_View> {
  final _scrollController = ScrollController();
  final _zoom = TransformationController();
  int? _totalPages;

  /// Whether the score is currently magnified.
  ///
  /// Drives [InteractiveViewer.panEnabled]: at rest panning stays off so
  /// vertical drags reach the page list and scroll it as usual, and it turns
  /// on only once zoomed, when dragging should move the magnified page
  /// instead. Without that switch the viewer swallows every drag and the
  /// score can no longer be scrolled at all.
  bool _isZoomed = false;

  /// Where a double tap landed, so the zoom centres on the bar the reader
  /// actually pointed at rather than the middle of the page.
  Offset? _doubleTapPoint;

  static const double _maxScale = 4.0;
  static const double _doubleTapScale = 2.5;

  // Previously a failure here just left _totalPages null forever,
  // causing the view to remain on the loading spinner with no way
  // to tell that the initial score load had actually failed.
  Object? _initialLoadError;

  @override
  void initState() {
    super.initState();

    _zoom.addListener(_onZoomChanged);

    // Kick off page 1 (and its prefetch of page 2) right away.
    widget.controller
        .warmPage(1)
        .then((_) {
          if (mounted) {
            setState(() {
              _totalPages = widget.controller.totalPages;
            });
          }
        })
        .catchError((Object error) {
          if (mounted) {
            setState(() {
              _initialLoadError = error;
            });
          }
        });
  }

  /// Only rebuilds when the zoomed/not-zoomed state actually flips, rather
  /// than on every frame of a pinch, which would rebuild the whole page list
  /// continuously while the gesture is in flight.
  void _onZoomChanged() {
    final zoomed = _zoom.value.getMaxScaleOnAxis() > 1.01;
    if (zoomed != _isZoomed) {
      setState(() => _isZoomed = zoomed);
    }
  }

  void _handleDoubleTap() {
    if (_isZoomed) {
      _zoom.value = Matrix4.identity();
      return;
    }
    final point = _doubleTapPoint;
    if (point == null) return;
    // Scale about the tapped point: translate it to the origin, scale, then
    // translate back.
    _zoom.value = Matrix4.identity()
      ..translateByDouble(point.dx, point.dy, 0, 1)
      ..scaleByDouble(_doubleTapScale, _doubleTapScale, 1, 1)
      ..translateByDouble(-point.dx, -point.dy, 0, 1);
  }

  @override
  void dispose() {
    _zoom.removeListener(_onZoomChanged);
    _zoom.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_initialLoadError != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            "Couldn't load score: $_initialLoadError",
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.black.withValues(alpha: 0.6)),
          ),
        ),
      );
    }

    if (_totalPages == null) {
      return const Center(child: CircularProgressIndicator(strokeWidth: 2.5));
    }

    return GestureDetector(
      onDoubleTapDown: (details) => _doubleTapPoint = details.localPosition,
      onDoubleTap: _handleDoubleTap,
      child: InteractiveViewer(
        transformationController: _zoom,
        minScale: 1.0,
        maxScale: _maxScale,
        panEnabled: _isZoomed,
        // Keeps the magnified score inside the paper frame instead of
        // sliding out over the surrounding controls.
        clipBehavior: Clip.hardEdge,
        child: _pages(),
      ),
    );
  }

  Widget _pages() {
    return Scrollbar(
      controller: _scrollController,
      thumbVisibility: true,
      child: ListView.separated(
        controller: _scrollController,
        padding: const EdgeInsets.fromLTRB(6, 38, 6, 18),
        itemCount: _totalPages!,
        separatorBuilder: (_, _) => const SizedBox(height: 18),
        itemBuilder: (context, index) {
          final pageNumber = index + 1;
          // warmPage also starts the next valid page in the background.
          widget.controller.warmPage(pageNumber);

          return FutureBuilder<RenderedPage>(
            future: widget.controller.getPage(pageNumber),
            builder: (context, snapshot) {
              if (snapshot.hasError) {
                return Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(
                      "Couldn't load page $pageNumber: ${snapshot.error}",
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: Colors.black.withValues(alpha: 0.6),
                      ),
                    ),
                  ),
                );
              }

              if (!snapshot.hasData) {
                return const Center(
                  child: CircularProgressIndicator(strokeWidth: 2.5),
                );
              }

              return snapshot.data!.widget;
            },
          );
        },
      ),
    );
  }
}
