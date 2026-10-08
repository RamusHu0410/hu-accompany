import 'dart:math';
import 'package:flutter/material.dart';

/// A vinyl record, painted procedurally so it never needs an image asset.
/// Grooves are drawn as many thin concentric rings with slightly randomized
/// (but seeded/stable) shading, plus two soft specular sweeps that sell the
/// "light hitting glossy black plastic" look. The rotation is applied via
/// [Transform.rotate] around this widget's own center, so callers just feed
/// it an angle in radians and it always spins around its middle.
class VinylDisk extends StatelessWidget {
  final double size;
  final double rotation; // radians
  final String label;
  final String? sublabel;
  final Color labelColor;
  final Color diskColor;

  const VinylDisk({
    super.key,
    required this.size,
    required this.rotation,
    required this.label,
    this.sublabel,
    this.labelColor = const Color(0xFFEDE6DA),
    this.diskColor = const Color(0xFF0B0B0D),
  });

  @override
  Widget build(BuildContext context) {
    return Transform.rotate(
      angle: rotation,
      child: SizedBox(
        width: size,
        height: size,
        child: CustomPaint(
          painter: _VinylPainter(diskColor: diskColor),
          child: Center(
            child: _Label(
              size: size * 0.38,
              color: labelColor,
              title: label,
              subtitle: sublabel,
            ),
          ),
        ),
      ),
    );
  }
}

class _VinylPainter extends CustomPainter {
  final Color diskColor;
  _VinylPainter({required this.diskColor});

  // Seeded so the groove pattern is identical every frame — only the
  // Transform.rotate wrapping this widget actually moves.
  static final Random _rng = Random(42);

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = size.width / 2;

    canvas.drawCircle(center, radius, Paint()..color = diskColor);

    // Groove rings, from just outside the label out to the edge.
    final labelRadius = radius * 0.38;
    const grooveCount = 150;
    for (int i = 0; i < grooveCount; i++) {
      final t = i / grooveCount;
      final r = labelRadius + (radius * 0.97 - labelRadius) * t;
      final wobble = 0.015 + _rng.nextDouble() * 0.02;
      final paint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 0.6
        ..color = Colors.white.withValues(
          alpha: (i.isEven ? 0.05 : 0.02) + wobble,
        );
      canvas.drawCircle(center, r, paint);
    }

    // Outer rim highlight
    canvas.drawCircle(
      center,
      radius * 0.985,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = radius * 0.03
        ..color = Colors.white.withValues(alpha: 0.06),
    );

    // Two soft specular sweeps — glossy black plastic catching light.
    _sweep(canvas, center, radius, startAngle: -0.9, sweep: 0.5, alpha: 0.10);
    _sweep(canvas, center, radius, startAngle: 2.1, sweep: 0.35, alpha: 0.06);

    // Spindle hole + a thin silver ring around it.
    canvas.drawCircle(
      center,
      radius * 0.045,
      Paint()..color = const Color(0xFF050505),
    );
    canvas.drawCircle(
      center,
      radius * 0.05,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1
        ..color = Colors.white.withValues(alpha: 0.15),
    );
  }

  void _sweep(
    Canvas canvas,
    Offset center,
    double radius, {
    required double startAngle,
    required double sweep,
    required double alpha,
  }) {
    final rect = Rect.fromCircle(center: center, radius: radius);
    final gradient = SweepGradient(
      startAngle: startAngle,
      endAngle: startAngle + sweep,
      colors: [
        Colors.white.withValues(alpha: 0),
        Colors.white.withValues(alpha: alpha),
        Colors.white.withValues(alpha: 0),
      ],
    );
    canvas.drawCircle(
      center,
      radius,
      Paint()..shader = gradient.createShader(rect),
    );
  }

  @override
  bool shouldRepaint(covariant _VinylPainter oldDelegate) =>
      oldDelegate.diskColor != diskColor;
}

class _Label extends StatelessWidget {
  final double size;
  final Color color;
  final String title;
  final String? subtitle;
  const _Label({
    required this.size,
    required this.color,
    required this.title,
    this.subtitle,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      padding: EdgeInsets.all(size * 0.14),
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: RadialGradient(
          colors: [Color.lerp(color, Colors.white, 0.08)!, color],
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.35),
            blurRadius: 6,
            spreadRadius: 1,
          ),
        ],
      ),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              title,
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: const Color(0xFF2B2B2B),
                fontWeight: FontWeight.w700,
                letterSpacing: 0.4,
                fontSize: size * 0.13,
              ),
            ),
            if (subtitle != null) ...[
              SizedBox(height: size * 0.04),
              Text(
                subtitle!,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: const Color(0xFF2B2B2B).withValues(alpha: 0.6),
                  fontSize: size * 0.08,
                  letterSpacing: 0.6,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
