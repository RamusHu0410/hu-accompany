import 'package:flutter/material.dart';
import '../screens/Music_Library_Page.dart';
import '../services/Send_Strings_2Server.dart';
import '../theme/Design_Tokens.dart';
import 'Library_Browse.dart';
import 'Press_Scale.dart';

// ═══════════════════════════════════════════════════════════════════════════════
// EDITION PICKER — bottom sheet shown when a tapped work has more than
// one version (different arrangers/instrumentations/editors).
// ═══════════════════════════════════════════════════════════════════════════════

class LibraryEditionPicker extends StatelessWidget {
  final WorkSummary work;
  final List<MusicSheet> editions;
  const LibraryEditionPicker({
    super.key,
    required this.work,
    required this.editions,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          Space.lg,
          Space.md,
          Space.lg,
          Space.xl,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 36,
                height: 4,
                margin: const EdgeInsets.only(bottom: Space.md),
                decoration: BoxDecoration(
                  color: libInk.withValues(alpha: 0.2),
                  borderRadius: Radii.pillRadius,
                ),
              ),
            ),
            Text(
              work.title,
              style: const TextStyle(
                fontFamily: libBookFont,
                fontFamilyFallback: libBookFontFallback,
                color: libInk,
                fontSize: 17,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: Space.xxs),
            Text(
              '${editions.length} versions found — choose one',
              style: TextStyle(
                fontFamily: libBookFont,
                fontFamilyFallback: libBookFontFallback,
                fontStyle: FontStyle.italic,
                color: libInk.withValues(alpha: 0.5),
                fontSize: 13,
              ),
            ),
            const SizedBox(height: Space.md),
            Flexible(
              child: ListView.separated(
                shrinkWrap: true,
                physics: AppScroll.physics,
                itemCount: editions.length,
                separatorBuilder: (_, _) => const SizedBox(height: Space.xs),
                itemBuilder: (_, i) {
                  final edition = editions[i];
                  return PressScale(
                    onTap: () => Navigator.pop(context, edition),
                    borderRadius: Radii.cardRadius,
                    pressedScale: 0.98,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: Space.md,
                        vertical: Space.sm,
                      ),
                      decoration: BoxDecoration(
                        color: libInk.withValues(alpha: 0.06),
                        borderRadius: Radii.cardRadius,
                        border: Border.all(
                          color: libInk.withValues(alpha: 0.18),
                        ),
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              edition.title,
                              style: const TextStyle(
                                fontFamily: libBookFont,
                                fontFamilyFallback: libBookFontFallback,
                                color: libInk,
                                fontSize: 14,
                                fontWeight: FontWeight.w500,
                              ),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          const SizedBox(width: Space.xs),
                          Icon(
                            Icons.chevron_right_rounded,
                            size: 18,
                            color: libInk.withValues(alpha: 0.4),
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
