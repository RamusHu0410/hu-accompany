import 'package:flutter/material.dart';
import '../theme/Design_Tokens.dart';
import 'Library_Browse.dart';
import 'Shimmer.dart';

/// Stand-in rows shown while a search is in flight. Matches the real result
/// row's height, padding and internal rhythm so results land in place
/// instead of pushing a centred spinner out of the way.
class LibrarySkeleton extends StatelessWidget {
  final int rowCount;
  const LibrarySkeleton({super.key, this.rowCount = 5});

  @override
  Widget build(BuildContext context) {
    return Shimmer(
      base: libInk.withValues(alpha: 0.06),
      highlight: libInk.withValues(alpha: 0.13),
      child: ListView.separated(
        physics: const NeverScrollableScrollPhysics(),
        padding: const EdgeInsets.only(bottom: Space.xl),
        itemCount: rowCount,
        separatorBuilder: (_, _) => const SizedBox(height: Space.sm),
        itemBuilder: (_, _) => const _SkeletonRow(),
      ),
    );
  }
}

class _SkeletonRow extends StatelessWidget {
  const _SkeletonRow();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: Space.md,
        vertical: Space.sm,
      ),
      decoration: BoxDecoration(
        color: libCreamCard,
        borderRadius: Radii.modalRadius,
        border: Border.all(color: libInk.withValues(alpha: 0.10)),
      ),
      child: const Row(
        children: [
          SkeletonBox(
            width: 36,
            height: 36,
            borderRadius: Radii.pillRadius,
          ),
          SizedBox(width: Space.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                SkeletonBox(height: 11, borderRadius: Radii.pillRadius),
                SizedBox(height: Space.xs),
                FractionallySizedBox(
                  alignment: Alignment.centerLeft,
                  widthFactor: 0.45,
                  child: SkeletonBox(
                    height: 9,
                    borderRadius: Radii.pillRadius,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
