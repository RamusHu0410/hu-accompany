import 'package:flutter/material.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';
import 'package:hu_accomponist/shared/ui/Shimmer.dart';

/// Placeholder shown while the shelf reads from storage.
///
/// Mirrors the real grid's geometry exactly — same padding, same cross-axis
/// count, same aspect ratio, same two text lines under each cover — so the
/// swap to real content is a crossfade in place rather than a reflow. A
/// spinner can't do that: it occupies none of the space the content will,
/// so every tile jumps when it arrives.
class ShelfSkeleton extends StatelessWidget {
  final Brightness brightness;

  /// Matches the shelf's own first-section length, so the placeholder
  /// implies roughly the right amount of content.
  final int tileCount;

  const ShelfSkeleton({
    super.key,
    required this.brightness,
    this.tileCount = 6,
  });

  @override
  Widget build(BuildContext context) {
    final text = ShelfPalette.textColor(brightness);

    return Shimmer(
      base: text.withValues(alpha: 0.07),
      highlight: text.withValues(alpha: 0.14),
      child: CustomScrollView(
        physics: const NeverScrollableScrollPhysics(),
        slivers: [
          const SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                Space.lg,
                Space.lg,
                Space.lg,
                Space.sm,
              ),
              child: SkeletonBox(
                width: 132,
                height: 16,
                borderRadius: Radii.pillRadius,
              ),
            ),
          ),
          SliverPadding(
            padding: const EdgeInsets.symmetric(horizontal: Space.lg),
            sliver: SliverGrid(
              gridDelegate:
                  const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 3,
                    mainAxisSpacing: Space.md,
                    crossAxisSpacing: Space.sm,
                    childAspectRatio: 0.54,
                  ),
              delegate: SliverChildBuilderDelegate(
                (context, _) => const _SkeletonTile(),
                childCount: tileCount,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SkeletonTile extends StatelessWidget {
  const _SkeletonTile();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        AspectRatio(
          aspectRatio: 0.78,
          child: SkeletonBox(height: double.infinity),
        ),
        SizedBox(height: Space.xs),
        SkeletonBox(
          height: 9,
          borderRadius: Radii.pillRadius,
        ),
        SizedBox(height: Space.xxs + 2),
        FractionallySizedBox(
          alignment: Alignment.centerLeft,
          widthFactor: 0.6,
          child: SkeletonBox(height: 8, borderRadius: Radii.pillRadius),
        ),
      ],
    );
  }
}
