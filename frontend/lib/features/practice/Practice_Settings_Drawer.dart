import 'package:flutter/material.dart';
import 'package:hu_accomponist/features/practice/Phrase_Feedback.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';
import 'package:hu_accomponist/shared/ui/Press_Scale.dart';

/// The practice screen's side drawer: current recording and phrase status,
/// plus the two actions that don't belong on the score itself.
class PracticeSettingsDrawer extends StatelessWidget {
  final bool isRecording;
  final bool hasScore;
  final PhraseFeedback feedback;
  final VoidCallback onOpenLibrary;
  final VoidCallback onClearAnnotations;

  const PracticeSettingsDrawer({
    super.key,
    required this.isRecording,
    required this.hasScore,
    required this.feedback,
    required this.onOpenLibrary,
    required this.onClearAnnotations,
  });

  static Color feedbackColor(PhraseFeedback feedback) => switch (feedback) {
    PhraseFeedback.good => PracticePalette.gold,
    PhraseFeedback.fair => PracticePalette.caution,
    PhraseFeedback.off => PracticePalette.alert,
    PhraseFeedback.none => PracticePalette.mutedBrown,
  };

  @override
  Widget build(BuildContext context) {
    final feedbackLabel = switch (feedback) {
      PhraseFeedback.good => 'Last phrase — on pitch',
      PhraseFeedback.fair => 'Last phrase — roughly there',
      PhraseFeedback.off => 'Last phrase — off pitch',
      PhraseFeedback.none => 'No phrase analyzed yet',
    };

    return Drawer(
      backgroundColor: PracticePalette.paper,
      child: SafeArea(
        child: ListView(
          physics: AppScroll.physics,
          padding: const EdgeInsets.fromLTRB(
            Space.lg,
            Space.xl,
            Space.lg,
            Space.xxl,
          ),
          children: [
            const Text(
              'SETTINGS',
              style: TextStyle(
                color: PracticePalette.gold,
                fontSize: 11,
                letterSpacing: 2.4,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: Space.xs),
            const Text(
              'Practice',
              style: TextStyle(
                color: PracticePalette.brown,
                fontSize: 22,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: Space.xl),
            _StatusRow(
              icon: isRecording ? Icons.mic_rounded : Icons.mic_none_rounded,
              iconColor: isRecording
                  ? PracticePalette.alert
                  : PracticePalette.gold,
              label: isRecording ? 'Recording is active' : 'Ready to record',
            ),
            const SizedBox(height: Space.md),
            _StatusRow(
              icon: Icons.graphic_eq_rounded,
              iconColor: feedbackColor(feedback),
              label: feedbackLabel,
            ),
            const Divider(height: Space.xxxl, color: PracticePalette.lightGold),
            _DrawerAction(
              icon: Icons.library_music_outlined,
              label: hasScore ? 'Change score' : 'Open the library',
              onTap: onOpenLibrary,
            ),
            _DrawerAction(
              icon: Icons.layers_clear_outlined,
              label: 'Clear annotations',
              onTap: onClearAnnotations,
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusRow extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String label;

  const _StatusRow({
    required this.icon,
    required this.iconColor,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        // Animated so a phrase verdict or a recording start reads as the
        // same row changing state, rather than as the row being replaced.
        AnimatedContainer(
          duration: Motion.base,
          curve: Motion.standard,
          width: 28,
          height: 28,
          decoration: BoxDecoration(
            color: iconColor.withValues(alpha: 0.12),
            shape: BoxShape.circle,
          ),
          child: Icon(icon, size: 16, color: iconColor),
        ),
        const SizedBox(width: Space.sm),
        Expanded(
          child: Text(
            label,
            style: const TextStyle(
              color: PracticePalette.brown,
              fontSize: 14,
            ),
          ),
        ),
      ],
    );
  }
}

class _DrawerAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _DrawerAction({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return PressScale(
      onTap: onTap,
      borderRadius: Radii.cardRadius,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: Space.sm),
        child: Row(
          children: [
            Icon(icon, size: 20, color: PracticePalette.gold),
            const SizedBox(width: Space.md),
            Expanded(
              child: Text(
                label,
                style: const TextStyle(
                  color: PracticePalette.brown,
                  fontSize: 15,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
