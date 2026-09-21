import 'dart:math';
import 'package:flutter/material.dart';
import 'package:hu_accomponist/features/practice/Note_Burst_Controller.dart';
import 'package:flutter/scheduler.dart';

/// Paints whatever particles [controller] currently holds, and drives its
/// own frame-by-frame ticking via [controller.tick] using
/// [getAngularVelocity] for the disk's live spin speed.
///
/// Purely a rendering layer — all spawn/physics logic lives in
/// NoteBurstController (Note_Burst_Controller.dart), so this file only
/// cares about drawing.
class NoteBurstLayer extends StatefulWidget {
  final NoteBurstController controller;
  final double diskSize;
  final double Function() getAngularVelocity;
  final VoidCallback? onNoteSpawned;

  const NoteBurstLayer({
    super.key,
    required this.controller,
    required this.diskSize,
    required this.getAngularVelocity,
    this.onNoteSpawned,
  });

  @override
  State<NoteBurstLayer> createState() => _NoteBurstLayerState();
}

class _NoteBurstLayerState extends State<NoteBurstLayer>
    with SingleTickerProviderStateMixin {
  late final Ticker _ticker;
  Duration _lastElapsed = Duration.zero;

  @override
  void initState() {
    super.initState();
    _ticker = createTicker(_onTick)..start();
  }

  void _onTick(Duration elapsed) {
    final dt = (elapsed - _lastElapsed).inMicroseconds / 1e6;
    _lastElapsed = elapsed;
    // Skip the very first frame (dt == 0) and any freak long gap (e.g.
    // after a hot reload or the app resuming from background).
    if (dt <= 0 || dt > 0.1) return;

    final before = widget.controller.particles.length;
    widget.controller.tick(
      dt,
      angularVelocity: widget.getAngularVelocity(),
      diskRadius: widget.diskSize / 2,
    );
    if (widget.controller.particles.length > before) {
      widget.onNoteSpawned?.call();
    }
  }

  @override
  void dispose() {
    _ticker.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Sized well beyond the disk itself so notes have room to travel
    // outward before they fully fade — never affects layout/hit-testing
    // since the caller wraps this in IgnorePointer and the Stack it sits
    // in clips nothing.
    final overlaySize = widget.diskSize * 2.2;
    return SizedBox(
      width: overlaySize,
      height: overlaySize,
      child: AnimatedBuilder(
        animation: widget.controller,
        builder: (context, _) =>
            CustomPaint(painter: _NoteBurstPainter(widget.controller.particles)),
      ),
    );
  }
}

class _NoteBurstPainter extends CustomPainter {
  final List<NoteParticle> particles;
  _NoteBurstPainter(this.particles);

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);

    for (final p in particles) {
      final opacity = 1 - p.t;
      if (opacity <= 0) continue;

      final pos = center + Offset(cos(p.angle), sin(p.angle)) * p.radius;
      final scale = 1.0 - p.t * 0.25;

      // "Losing its color" — drifts from white toward a dim grey as it
      // fades, rather than just dropping alpha on a static white glyph.
      final color = Color.lerp(
        Colors.white,
        const Color(0xFF6B6B6B),
        p.t,
      )!.withValues(alpha: opacity);

      final textPainter = TextPainter(
        text: TextSpan(
          text: p.glyph,
          style: TextStyle(fontSize: p.baseSize, color: color),
        ),
        textDirection: TextDirection.ltr,
      )..layout();

      canvas.save();
      canvas.translate(pos.dx, pos.dy);
      canvas.rotate(p.spin);
      canvas.scale(scale);
      textPainter.paint(
        canvas,
        Offset(-textPainter.width / 2, -textPainter.height / 2),
      );
      canvas.restore();
    }
  }

  @override
  bool shouldRepaint(covariant _NoteBurstPainter oldDelegate) => true;
}