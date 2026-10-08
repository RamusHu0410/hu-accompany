import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';

/// The hummed notes on a piano roll: pitch up the side, time across. Notes
/// that are sounding light up, and a line follows the playback.
class RawPianoRoll extends StatelessWidget {
  const RawPianoRoll({
    super.key,
    required this.hum,
    required this.sounding,
    required this.position,
    required this.isPlaying,
    this.height = 150,
  });

  final RawHum hum;
  final Set<int> sounding;
  final double position;
  final bool isPlaying;
  final double height;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: height,
      width: double.infinity,
      child: CustomPaint(
        painter: RawPianoRollPainter(
          notes: hum.notes,
          duration: hum.duration,
          sounding: sounding,
          playhead: isPlaying ? position : null,
        ),
      ),
    );
  }
}

class RawPianoRollPainter extends CustomPainter {
  RawPianoRollPainter({
    required this.notes,
    required this.duration,
    required this.sounding,
    required this.playhead,
  });

  final List<HumNote> notes;
  final double duration;
  final Set<int> sounding;
  final double? playhead;

  static const double _labelWidth = 30;
  static const double _pad = 6;
  static const _names = [
    'C',
    'C#',
    'D',
    'Eb',
    'E',
    'F',
    'F#',
    'G',
    'Ab',
    'A',
    'Bb',
    'B',
  ];

  @override
  void paint(Canvas canvas, Size size) {
    if (notes.isEmpty) return;
    final low = notes.map((n) => n.midi.round()).reduce(math.min) - 1;
    final high = notes.map((n) => n.midi.round()).reduce(math.max) + 1;
    final rows = high - low + 1;
    final rowHeight = (size.height - _pad * 2) / rows;
    final left = _labelWidth;
    final width = size.width - left - _pad;
    final seconds = math.max(duration, 0.5);

    double yOf(int midi) => _pad + (high - midi) * rowHeight;
    double xOf(double time) => left + time / seconds * width;

    // Black-key rows shaded, like a piano roll, and a name on every C.
    final shade = Paint()
      ..color = PracticePalette.lightGold.withValues(alpha: 0.12);
    for (var midi = low; midi <= high; midi++) {
      if ([1, 3, 6, 8, 10].contains(midi % 12)) {
        canvas.drawRect(
          Rect.fromLTWH(left, yOf(midi), width, rowHeight),
          shade,
        );
      }
      if (midi % 12 == 0 || midi == low + 1) {
        _label(
          canvas,
          '${_names[midi % 12]}${midi ~/ 12 - 1}',
          Offset(2, yOf(midi) + rowHeight / 2),
        );
      }
    }

    for (var i = 0; i < notes.length; i++) {
      final note = notes[i];
      final lit = sounding.contains(i);
      final rect = RRect.fromRectAndRadius(
        Rect.fromLTWH(
          xOf(note.start),
          yOf(note.midi.round()) + 1,
          math.max(xOf(note.end) - xOf(note.start) - 1, 3),
          math.max(rowHeight - 2, 3),
        ),
        const Radius.circular(3),
      );
      if (lit) {
        canvas.drawRRect(
          rect.inflate(3),
          Paint()
            ..color = PracticePalette.gold.withValues(alpha: 0.35)
            ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4),
        );
      }
      // Louder notes are drawn stronger, so the dynamics of the hum show.
      final strength = 0.45 + 0.55 * (note.velocity / 127);
      canvas.drawRRect(
        rect,
        Paint()
          ..color = (lit ? PracticePalette.gold : PracticePalette.mutedBrown)
              .withValues(alpha: lit ? 1 : strength * 0.75),
      );
    }

    final at = playhead;
    if (at != null) {
      final x = xOf(at.clamp(0, seconds));
      canvas.drawLine(
        Offset(x, 0),
        Offset(x, size.height),
        Paint()
          ..color = PracticePalette.alert
          ..strokeWidth = 1.5,
      );
    }
  }

  void _label(Canvas canvas, String text, Offset at) {
    final painter = TextPainter(
      text: TextSpan(
        text: text,
        style: const TextStyle(color: PracticePalette.mutedBrown, fontSize: 9),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    painter.paint(canvas, at - Offset(0, painter.height / 2));
  }

  @override
  bool shouldRepaint(RawPianoRollPainter old) =>
      old.playhead != playhead ||
      !identical(old.notes, notes) ||
      old.sounding.length != sounding.length ||
      !old.sounding.containsAll(sounding);
}
