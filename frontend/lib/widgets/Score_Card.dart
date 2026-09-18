import 'package:flutter/material.dart';

/// One score on the shelf. [gradient] stands in for cover art until real
/// thumbnails exist — each piece gets a stable pair of tones so the grid
/// stays scannable.
class ShelfScore {
  final String title;
  final String composer;
  final String meta;
  final List<Color> gradient;

  const ShelfScore({
    required this.title,
    required this.composer,
    required this.meta,
    required this.gradient,
  });
}

class ScoreCard extends StatelessWidget {
  final ShelfScore score;
  final VoidCallback onTap;

  /// Caller-supplied so the card reads correctly against either of the
  /// shelf's two base surfaces (see Color_Theme.dart) instead of assuming
  /// a fixed dark background.
  final Color titleColor;
  final Color subtitleColor;

  const ScoreCard({
    super.key,
    required this.score,
    required this.onTap,
    required this.titleColor,
    required this.subtitleColor,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AspectRatio(
              aspectRatio: 0.78,
              child: Container(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(8),
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: score.gradient,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.35),
                      blurRadius: 8,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: Stack(
                  children: [
                    // The spine line that reads as a bound score.
                    Positioned(
                      left: 9,
                      top: 10,
                      bottom: 10,
                      child: Container(
                        width: 1,
                        color: Colors.white.withValues(alpha: 0.18),
                      ),
                    ),
                    Center(
                      child: Icon(
                        Icons.music_note_rounded,
                        size: 26,
                        color: Colors.white.withValues(alpha: 0.30),
                      ),
                    ),
                    Positioned(
                      left: 8,
                      right: 8,
                      bottom: 7,
                      child: Text(
                        score.meta,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 9,
                          letterSpacing: 0.6,
                          color: Colors.white.withValues(alpha: 0.75),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              score.title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: titleColor,
                fontSize: 12,
                height: 1.25,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              score.composer,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(color: subtitleColor, fontSize: 10.5),
            ),
          ],
        ),
      ),
    );
  }
}
