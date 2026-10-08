import 'package:flutter/material.dart';
import '../theme/Design_Tokens.dart';

/// Empty shelf. Draws three tilted, empty sleeves so the space reads as a
/// shelf that hasn't been filled yet rather than as a screen that failed to
/// load — and says plainly what puts something on it.
class ShelfEmpty extends StatelessWidget {
  final Color textColor;
  const ShelfEmpty({super.key, required this.textColor});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.xxxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _EmptySleeves(textColor: textColor),
            const SizedBox(height: Space.xl),
            Text(
              'Your shelf is empty',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: textColor.withValues(alpha: 0.85),
                fontSize: 16,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.2,
              ),
            ),
            const SizedBox(height: Space.xs),
            Text(
              'Open a score from the library and it will\nfind its way here.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: textColor.withValues(alpha: 0.5),
                fontSize: 13,
                height: 1.45,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _EmptySleeves extends StatelessWidget {
  final Color textColor;
  const _EmptySleeves({required this.textColor});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 108,
      height: 84,
      child: Stack(
        alignment: Alignment.center,
        children: [
          _sleeve(angle: -0.22, dx: -26, alpha: 0.10),
          _sleeve(angle: 0.22, dx: 26, alpha: 0.10),
          _sleeve(angle: 0, dx: 0, alpha: 0.16, child: true),
        ],
      ),
    );
  }

  Widget _sleeve({
    required double angle,
    required double dx,
    required double alpha,
    bool child = false,
  }) {
    return Transform.translate(
      offset: Offset(dx, 0),
      child: Transform.rotate(
        angle: angle,
        child: Container(
          width: 56,
          height: 72,
          decoration: BoxDecoration(
            color: textColor.withValues(alpha: alpha * 0.35),
            borderRadius: Radii.cardRadius,
            border: Border.all(color: textColor.withValues(alpha: alpha)),
          ),
          child: child
              ? Icon(
                  Icons.music_note_rounded,
                  size: 22,
                  color: textColor.withValues(alpha: 0.35),
                )
              : null,
        ),
      ),
    );
  }
}
