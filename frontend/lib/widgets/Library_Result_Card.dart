import 'package:flutter/material.dart';
import '../theme/Design_Tokens.dart';
import 'Library_Browse.dart';
import 'Press_Scale.dart';

// ═══════════════════════════════════════════════════════════════════════════════
// RESULT CARD — a clean pill-shaped row, tap to open.
// ═══════════════════════════════════════════════════════════════════════════════

class LibraryResultCard extends StatelessWidget {
  final String title;
  final String composer;
  final VoidCallback onTap;
  final VoidCallback onFavorite;
  const LibraryResultCard({
    super.key,
    required this.title,
    required this.composer,
    required this.onTap,
    required this.onFavorite,
  });

  @override
  Widget build(BuildContext context) {
    return PressScale(
      onTap: onTap,
      borderRadius: Radii.modalRadius,
      // Full-width target, so a shallower dip reads as the same give a
      // small tile gets from a deeper one.
      pressedScale: 0.985,
      splashColor: libGold.withValues(alpha: 0.08),
      highlightColor: libGold.withValues(alpha: 0.05),
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: Space.md,
          vertical: Space.sm,
        ),
        decoration: BoxDecoration(
          color: libCreamCard,
          borderRadius: Radii.modalRadius,
          border: Border.all(color: libInk.withValues(alpha: 0.10)),
          boxShadow: Elevations.card(Colors.black),
        ),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: libGold.withValues(alpha: 0.14),
                shape: BoxShape.circle,
              ),
              child: Icon(Icons.music_note_rounded, size: 18, color: libGold),
            ),
            const SizedBox(width: Space.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontFamily: libBookFont,
                      fontFamilyFallback: libBookFontFallback,
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                      color: libInk,
                    ),
                  ),
                  if (composer.isNotEmpty) ...[
                    const SizedBox(height: Space.xxs),
                    Text(
                      composer,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontFamily: libBookFont,
                        fontFamilyFallback: libBookFontFallback,
                        fontStyle: FontStyle.italic,
                        fontSize: 12,
                        color: libInk.withValues(alpha: 0.5),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: Space.xs),
            _FavouriteStar(title: title, onFavorite: onFavorite),
            const SizedBox(width: Space.xxs),
            Icon(Icons.chevron_right_rounded, size: 18, color: libGold),
          ],
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Close button — top-right corner
// ═══════════════════════════════════════════════════════════════════════════════
class LibraryCloseButton extends StatelessWidget {
  const LibraryCloseButton({super.key});
  @override
  Widget build(BuildContext context) {
    return PressScale(
      onTap: () => Navigator.pop(context),
      borderRadius: Radii.pillRadius,
      pressedScale: 0.9,
      child: Container(
        width: 32,
        height: 32,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: libCreamCard,
          border: Border.all(color: libInk.withValues(alpha: 0.16)),
        ),
        child: Icon(
          Icons.close_rounded,
          size: 16,
          color: libInk.withValues(alpha: 0.6),
        ),
      ),
    );
  }
}

/// Pulled out so toggling a favourite animates just the star, and so its
/// tap target is a comfortable size without enlarging the row's own.
class _FavouriteStar extends StatelessWidget {
  final String title;
  final VoidCallback onFavorite;
  const _FavouriteStar({required this.title, required this.onFavorite});

  @override
  Widget build(BuildContext context) {
    final isFavorite = LibraryShelfStore.isFavorite(title);
    return PressScale(
      onTap: onFavorite,
      borderRadius: Radii.pillRadius,
      pressedScale: 0.8,
      haptic: PressHaptic.light,
      child: Padding(
        padding: const EdgeInsets.all(Space.xxs),
        child: AnimatedSwitcher(
          duration: Motion.fast,
          transitionBuilder: (child, animation) => ScaleTransition(
            scale: animation,
            child: FadeTransition(opacity: animation, child: child),
          ),
          child: Icon(
            isFavorite ? Icons.star_rounded : Icons.star_border_rounded,
            key: ValueKey(isFavorite),
            size: 19,
            color: isFavorite ? libGold : libInk.withValues(alpha: 0.28),
          ),
        ),
      ),
    );
  }
}
