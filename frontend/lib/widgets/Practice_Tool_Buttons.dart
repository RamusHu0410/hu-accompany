import 'package:flutter/material.dart';
import '../theme/Color_Theme.dart';
import '../theme/Design_Tokens.dart';
import 'Press_Scale.dart';

/// The round tool buttons along the top of the score — settings, pen,
/// undo, palette. [active] fills the button rather than outlining it.
class PracticeToolButton extends StatelessWidget {
  final IconData icon;
  final bool active;
  final bool enabled;
  final Color color;
  final VoidCallback onTap;

  const PracticeToolButton({
    super.key,
    required this.icon,
    required this.active,
    required this.color,
    required this.onTap,
    this.enabled = true,
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedOpacity(
      duration: Motion.fast,
      opacity: enabled ? 1 : 0.35,
      child: PressScale(
        onTap: enabled ? onTap : null,
        borderRadius: Radii.pillRadius,
        haptic: PressHaptic.selection,
        child: AnimatedContainer(
          duration: Motion.fast,
          curve: Motion.standard,
          width: 46,
          height: 46,
          decoration: BoxDecoration(
            color: active ? color : PracticePalette.paper,
            shape: BoxShape.circle,
            border: Border.all(
              color: active ? color : PracticePalette.lightGold,
              width: 1,
            ),
            boxShadow: active
                ? [
                    BoxShadow(
                      color: color.withValues(alpha: 0.18),
                      blurRadius: 10,
                      offset: const Offset(0, 3),
                    ),
                  ]
                : Elevations.card(PracticePalette.brown),
          ),
          child: Icon(
            icon,
            size: 20,
            color: active ? PracticePalette.paper : color,
          ),
        ),
      ),
    );
  }
}

/// The two bottom-corner actions on the score screen — open the library,
/// and leave it.
class PracticeBottomButton extends StatelessWidget {
  final IconData icon;
  final Color color;
  final VoidCallback onTap;

  const PracticeBottomButton({
    super.key,
    required this.icon,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return PressScale(
      onTap: onTap,
      borderRadius: Radii.pillRadius,
      haptic: PressHaptic.selection,
      child: Container(
        width: 48,
        height: 48,
        decoration: BoxDecoration(
          color: PracticePalette.paper,
          shape: BoxShape.circle,
          border: Border.all(color: PracticePalette.lightGold, width: 1),
          boxShadow: Elevations.card(PracticePalette.brown),
        ),
        child: Icon(icon, size: 20, color: color),
      ),
    );
  }
}
