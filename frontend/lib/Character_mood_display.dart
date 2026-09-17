import 'package:flutter/material.dart';

/// Shows the companion's current sprite with a short DDLC-style "pop"
/// whenever [assetPath] changes — a quick bounce-overshoot scale layered
/// on top of a fade, rather than a flat crossfade. Used uniformly for
/// every mood swap (into enjoying, into mad, back to normal) as well as
/// switching between character types, since both just change [assetPath].
class CharacterMoodDisplay extends StatelessWidget {
  final String assetPath;
  final double width;
  final double height;
  final Alignment alignment;

  const CharacterMoodDisplay({
    super.key,
    required this.assetPath,
    required this.width,
    required this.height,
    this.alignment = Alignment.bottomRight,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      height: height,
      child: AnimatedSwitcher(
        duration: const Duration(milliseconds: 260),
        // easeOutBack briefly overshoots past 1.0 before settling — that
        // overshoot IS the "little bounce for a very short second."
        // Outgoing sprite just eases out, no overshoot on the way out.
        switchInCurve: Curves.easeOutBack,
        switchOutCurve: Curves.easeIn,
        transitionBuilder: (child, animation) {
          return FadeTransition(
            opacity: animation,
            child: ScaleTransition(scale: animation, child: child),
          );
        },
        child: Image.asset(
          assetPath,
          key: ValueKey(assetPath),
          fit: BoxFit.contain,
          alignment: alignment,
        ),
      ),
    );
  }
}