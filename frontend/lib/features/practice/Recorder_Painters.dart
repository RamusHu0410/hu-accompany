import 'dart:math';
import 'package:flutter/material.dart';

/// Two soft rings expanding out of the button — barely-there when idle,
/// firmer while recording.
class RecorderPulseHaloPainter extends CustomPainter {
  final double progress;
  final Color color;
  final double strength;

  RecorderPulseHaloPainter({
    required this.progress,
    required this.color,
    required this.strength,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    for (int i = 0; i < 2; i++) {
      final t = (progress + i * 0.5) % 1.0;
      final radius = 32 + t * 18;
      final opacity = strength * (1 - t);
      if (opacity <= 0.01) continue;
      canvas.drawCircle(
        center,
        radius,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.4
          ..color = color.withValues(alpha: opacity),
      );
    }
  }

  @override
  bool shouldRepaint(RecorderPulseHaloPainter old) =>
      old.progress != progress || old.color != color || old.strength != strength;
}

/// Five bars that stay flat-ish as a hint when idle and sway while
/// recording, so the button reads as "listening" without extra chrome.
class RecorderWaveHintPainter extends CustomPainter {
  final double progress;
  final bool active;
  final Color color;

  RecorderWaveHintPainter({
    required this.progress,
    required this.active,
    required this.color,
  });

  @override
  void paint(Canvas canvas, Size size) {
    const barCount = 5;
    final gap = size.width / barCount;
    final midY = size.height / 2;
    final paint = Paint()
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 2.5
      ..color = color.withValues(alpha: active ? 0.75 : 0.35);

    for (int i = 0; i < barCount; i++) {
      final phase = (progress + i / barCount) * 2 * pi;
      final amplitude = active ? 5.0 : 1.6;
      final half = 1.5 + amplitude * (0.5 + 0.5 * sin(phase));
      final x = gap * (i + 0.5);
      canvas.drawLine(Offset(x, midY - half), Offset(x, midY + half), paint);
    }
  }

  @override
  bool shouldRepaint(RecorderWaveHintPainter old) =>
      old.progress != progress || old.active != active || old.color != color;
}