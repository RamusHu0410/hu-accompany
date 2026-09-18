import 'package:flutter/material.dart';
import '../theme/Design_Tokens.dart';
import 'Press_Scale.dart';

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
    return PressScale(
      onTap: onTap,
      borderRadius: Radii.cardRadius,
      // Small target, so it needs a touch more travel than a full-width
      // row to register as the same amount of give under the finger.
      pressedScale: 0.955,
      // The ripple is suppressed: it would wash across the cover's
      // gradient and read as a rendering artefact rather than feedback.
      splashColor: Colors.transparent,
      highlightColor: Colors.transparent,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AspectRatio(
            aspectRatio: 0.78,
            child: Container(
              decoration: BoxDecoration(
                borderRadius: Radii.cardRadius,
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: score.gradient,
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.28),
                    blurRadius: 10,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Stack(
                children: [
                  // The spine line that reads as a bound score.
                  Positioned(
                    left: Space.xs,
                    top: Space.sm,
                    bottom: Space.sm,
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
                    left: Space.xs,
                    right: Space.xs,
                    bottom: Space.xs,
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
          const SizedBox(height: Space.xs),
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
          const SizedBox(height: Space.xxs),
          Text(
            score.composer,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: subtitleColor,
              fontSize: 11,
              fontWeight: FontWeight.w400,
            ),
          ),
        ],
      ),
    );
  }
}
