import 'package:flutter/material.dart';

import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/integrations/hum/saved_hum_store.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// One saved song: its notes sketched on a card that plays it, and a menu
/// to rename or delete it.
class HummedSongRow extends StatelessWidget {
  const HummedSongRow({
    super.key,
    required this.song,
    required this.playing,
    required this.brightness,
    required this.onTap,
    required this.onRename,
    required this.onDelete,
  });

  final SavedHum song;
  final bool playing;
  final Brightness brightness;
  final VoidCallback onTap;
  final VoidCallback onRename;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final text = ShelfPalette.textColor(brightness);
    final colors = ShelfPalette.gradientFor(song.id);
    final details = [
      song.style,
      if (song.key.isNotEmpty) '${song.key} ${song.mode}',
      if (song.seconds > 0) _clock(song.seconds),
      _ago(song.savedAt),
    ].join('  ·  ');
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.sm),
      child: Material(
        color: text.withValues(alpha: 0.04),
        borderRadius: Radii.cardRadius,
        child: InkWell(
          borderRadius: Radii.cardRadius,
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.all(Space.sm),
            child: Row(
              children: [
                Container(
                  width: 64,
                  height: 64,
                  decoration: BoxDecoration(
                    borderRadius: Radii.cardRadius,
                    gradient: LinearGradient(
                      colors: colors,
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                  ),
                  child: Stack(
                    children: [
                      Positioned.fill(
                        child: CustomPaint(painter: _Sketch(song.sung)),
                      ),
                      Center(
                        child: Icon(
                          playing
                              ? Icons.stop_rounded
                              : Icons.play_arrow_rounded,
                          color: Colors.white,
                          size: 30,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: Space.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        song.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: text,
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        details,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: ShelfPalette.subtextColor(brightness),
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
                PopupMenuButton<String>(
                  key: ValueKey('hummed-menu-${song.id}'),
                  icon: Icon(
                    Icons.more_vert_rounded,
                    color: ShelfPalette.subtextColor(brightness),
                  ),
                  onSelected: (choice) =>
                      choice == 'rename' ? onRename() : onDelete(),
                  itemBuilder: (context) => const [
                    PopupMenuItem(value: 'rename', child: Text('Rename')),
                    PopupMenuItem(value: 'delete', child: Text('Delete')),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  static String _clock(double seconds) {
    final s = seconds.round();
    return '${s ~/ 60}:${(s % 60).toString().padLeft(2, '0')}';
  }

  static String _ago(DateTime savedAt) {
    final diff = DateTime.now().difference(savedAt);
    if (diff.inMinutes < 1) return 'Just now';
    if (diff.inHours < 1) return '${diff.inMinutes}m ago';
    if (diff.inDays < 1) return '${diff.inHours}h ago';
    if (diff.inDays < 7) return '${diff.inDays}d ago';
    return '${(diff.inDays / 7).floor()}w ago';
  }
}

/// The hummed notes as faint dashes across the card.
class _Sketch extends CustomPainter {
  _Sketch(this.notes);

  final List<HumNote> notes;

  @override
  void paint(Canvas canvas, Size size) {
    if (notes.isEmpty) return;
    final end = notes.map((n) => n.end).reduce((a, b) => a > b ? a : b);
    final low = notes.map((n) => n.midi).reduce((a, b) => a < b ? a : b);
    final high = notes.map((n) => n.midi).reduce((a, b) => a > b ? a : b);
    final span = (high - low).clamp(6, 48);
    final inset = size.width * 0.12;
    final paint = Paint()
      ..color = Colors.white.withValues(alpha: 0.35)
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    final width = size.width - 2 * inset, height = size.height - 2 * inset;
    for (final note in notes) {
      final y = inset + height * (1 - (note.midi - low) / span);
      final x0 = inset + width * note.start / end;
      final x1 = inset + width * note.end / end;
      canvas.drawLine(
        Offset(x0, y),
        Offset(x1 - 1.5 > x0 ? x1 - 1.5 : x0, y),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_Sketch old) => old.notes != notes;
}
