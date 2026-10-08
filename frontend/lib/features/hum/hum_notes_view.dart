import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// The notes you hummed (gold) over the notes the song plays (blue-grey),
/// as bars on a pitch-by-time grid.
class HumNotesView extends StatelessWidget {
  const HumNotesView({super.key, required this.notes, this.height = 150});

  final HumNotes notes;
  final double height;

  static const Color sungColor = PracticePalette.gold;
  static const Color playedColor = Color(0xFF5B7188);

  @override
  Widget build(BuildContext context) {
    return Container(
      height: height,
      decoration: BoxDecoration(
        color: PracticePalette.paper,
        borderRadius: Radii.cardRadius,
        border: Border.all(
          color: PracticePalette.lightGold.withValues(alpha: 0.65),
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: notes.isEmpty
          ? const Center(
              child: Text(
                'Your notes will show up here',
                style: TextStyle(
                  color: PracticePalette.mutedBrown,
                  fontSize: 13,
                ),
              ),
            )
          : Stack(
              children: [
                Positioned.fill(
                  child: CustomPaint(painter: HumNotesPainter(notes)),
                ),
                const Positioned(top: 8, right: 12, child: _Legend()),
              ],
            ),
    );
  }
}

class _Legend extends StatelessWidget {
  const _Legend();

  @override
  Widget build(BuildContext context) {
    Widget key(Color color, String label) => Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 10,
          height: 10,
          decoration: BoxDecoration(
            color: color,
            borderRadius: Radii.cardRadius,
          ),
        ),
        const SizedBox(width: Space.xxs),
        Text(
          label,
          style: const TextStyle(
            color: PracticePalette.mutedBrown,
            fontSize: 11,
          ),
        ),
      ],
    );
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        key(HumNotesView.sungColor, 'you'),
        const SizedBox(width: Space.sm),
        key(HumNotesView.playedColor, 'song'),
      ],
    );
  }
}

class HumNotesPainter extends CustomPainter {
  HumNotesPainter(this.notes);

  final HumNotes notes;

  static const double _margin = 14;
  static const double _topRoom = 26; // clear of the legend

  @override
  void paint(Canvas canvas, Size size) {
    final all = [...notes.sung, ...notes.played];
    if (all.isEmpty) return;

    final start = all.map((n) => n.start).reduce(math.min);
    final end = all.map((n) => n.end).reduce(math.max);
    final low = all.map((n) => n.midi).reduce(math.min) - 1;
    final high = all.map((n) => n.midi).reduce(math.max) + 1;
    final width = size.width - _margin * 2;
    final height = size.height - _margin - _topRoom;
    final seconds = math.max(end - start, 0.1);
    final semitones = math.max(high - low, 4.0);
    final barHeight = math.min(height / semitones, 10.0);

    void draw(List<HumNote> list, Color color) {
      final paint = Paint()..color = color;
      for (final note in list) {
        final x = _margin + (note.start - start) / seconds * width;
        final w = math.max(note.duration / seconds * width, 3.0);
        final y = _topRoom + height - (note.midi - low) / semitones * height;
        canvas.drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTWH(x, y - barHeight / 2, w, barHeight),
            Radius.circular(barHeight / 2),
          ),
          paint,
        );
      }
    }

    // The song underneath, so the hummed notes stay readable over it.
    draw(notes.played, HumNotesView.playedColor.withValues(alpha: 0.55));
    draw(notes.sung, HumNotesView.sungColor);
  }

  @override
  bool shouldRepaint(HumNotesPainter old) => old.notes != notes;
}
