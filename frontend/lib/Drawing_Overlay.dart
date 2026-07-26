import 'package:flutter/material.dart';

/// A single completed (or in-progress) pen stroke, locked in with the
/// color/width it was drawn with — changing the current pen settings
/// afterwards must NOT retroactively change strokes already on the canvas.
class _Stroke {
  final List<Offset> points;
  final Color color;
  final double strokeWidth;
  final bool isEraser;

  _Stroke({
    required this.points,
    required this.color,
    required this.strokeWidth,
    this.isEraser = false,
  });
}

class Drawing_Overlay extends StatefulWidget {
  final bool isDrawingMode;
  final bool isErasing;
  final Color penColor;
  final double penSize;
  final double eraserSize;
  const Drawing_Overlay({
    super.key,
    required this.isDrawingMode,
    this.isErasing = false,
    this.penColor = const Color(0xFFE94560),
    this.penSize = 3.0,
    this.eraserSize = 24.0,
  });

  @override
  State<Drawing_Overlay> createState() => _Drawing_OverlayState();
}

class _Drawing_OverlayState extends State<Drawing_Overlay> {
  final List<_Stroke> _strokes = [];
  _Stroke? _currentStroke;

  void _startStroke(Offset point) {
    // Snapshot the current tool *now* — this stroke keeps this
    // color/width/eraser-ness for its whole life, even if the user changes
    // the pen or eraser settings later.
    setState(() {
      _currentStroke = widget.isErasing
          ? _Stroke(
              points: [point],
              color: Colors.transparent,
              strokeWidth: widget.eraserSize,
              isEraser: true,
            )
          : _Stroke(
              points: [point],
              color: widget.penColor,
              strokeWidth: widget.penSize,
            );
    });
  }

  void _extendStroke(Offset point) {
    final stroke = _currentStroke;
    if (stroke == null) return;
    setState(() => stroke.points.add(point));
  }

  void _endStroke() {
    final stroke = _currentStroke;
    if (stroke != null && stroke.points.isNotEmpty) {
      setState(() {
        _strokes.add(stroke);
        _currentStroke = null;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final toolActive = widget.isDrawingMode || widget.isErasing;
    return GestureDetector(
      // Pass touches through when neither drawing nor erasing
      behavior: toolActive ? HitTestBehavior.opaque : HitTestBehavior.translucent,
      onPanStart: toolActive ? (d) => _startStroke(d.localPosition) : null,
      onPanUpdate: toolActive ? (d) => _extendStroke(d.localPosition) : null,
      onPanEnd: toolActive ? (d) => _endStroke() : null,
      child: CustomPaint(
        painter: _strokes.isNotEmpty || _currentStroke != null
            ? _StrokePainter(
                strokes: _strokes,
                currentStroke: _currentStroke,
              )
            : null, // no painter = no repaint cost when canvas is empty
      ),
    );
  }
}

class _StrokePainter extends CustomPainter {
  final List<_Stroke> strokes;
  final _Stroke? currentStroke;

  _StrokePainter({required this.strokes, required this.currentStroke});

  void _drawStroke(Canvas canvas, _Stroke stroke) {
    if (stroke.points.length < 2) return;
    final paint = Paint()
      ..color = stroke.isEraser ? Colors.black : stroke.color
      ..strokeWidth = stroke.strokeWidth
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..style = PaintingStyle.stroke
      // Eraser strokes clear pixels instead of painting over them, so they
      // remove ink from strokes drawn earlier in this same layer regardless
      // of color. Requires the saveLayer wrapper in paint() below — without
      // an offscreen layer, BlendMode.clear has nothing scoped to clear.
      ..blendMode = stroke.isEraser ? BlendMode.clear : BlendMode.srcOver;
    final path = Path()..moveTo(stroke.points[0].dx, stroke.points[0].dy);
    for (int i = 1; i < stroke.points.length; i++) {
      path.lineTo(stroke.points[i].dx, stroke.points[i].dy);
    }
    canvas.drawPath(path, paint);
  }

  @override
  void paint(Canvas canvas, Size size) {
    // All strokes for this frame are composited into one offscreen layer
    // first, so eraser strokes (BlendMode.clear) only punch through ink
    // drawn earlier in this same layer — not whatever's rendered beneath
    // the whole overlay widget in the tree.
    canvas.saveLayer(Offset.zero & size, Paint());
    for (final s in strokes) {
      _drawStroke(canvas, s);
    }
    if (currentStroke != null) {
      _drawStroke(canvas, currentStroke!);
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_StrokePainter old) => true;
}