import 'package:flutter/material.dart';

/// Palette for the Shelf screen. Two base surfaces (dark slate / light
/// slate) so the shelf adapts to the device's system appearance even
/// though the rest of the app is pinned to a light theme; the card
/// gradients are shared across both since each pair's darker stop keeps
/// the overlaid metadata text at or above WCAG AA contrast (4.5:1) either
/// way — see the ratios noted below.
class ShelfPalette {
  ShelfPalette._();

  // Base surfaces — replaces the old flat dark-brown (#3A2E22-ish) wash.
  static const Color baseDark = Color(0xFF1F2937); // slate-800
  static const Color baseLight = Color(0xFFEEF0F3); // slate-50

  static const Color textOnDark = Color(0xFFEDE6DA); // parchment
  static const Color textOnLight = Color(0xFF1F2937); // slate-800

  static Color base(Brightness brightness) =>
      brightness == Brightness.dark ? baseDark : baseLight;

  static Color textColor(Brightness brightness) =>
      brightness == Brightness.dark ? textOnDark : textOnLight;

  static Color subtextColor(Brightness brightness) =>
      textColor(brightness).withValues(alpha: 0.55);

  static Color cardBorder(Brightness brightness) =>
      textColor(brightness).withValues(alpha: 0.08);

  // Muted two-tone gradients — lavender, teal, dusty rose, sage — cycled
  // across cards regardless of section. Each pair's second stop is dark
  // enough that white meta text clears WCAG AA's 4.5:1 against it (e.g.
  // lavender's #4A3F73 vs white ≈ 9.3:1; sage's #3E5934 vs white ≈
  // 7.8:1), computed via the standard relative-luminance formula.
  static const List<List<Color>> cardGradients = [
    [Color(0xFF9B8FC4), Color(0xFF4A3F73)], // lavender
    [Color(0xFF5FA39F), Color(0xFF244744)], // teal
    [Color(0xFFD59AA3), Color(0xFF7A414B)], // dusty rose
    [Color(0xFF9BC08A), Color(0xFF3E5934)], // sage
  ];

  /// Deterministic so the same sheet always gets the same card color
  /// across reloads, without persisting a color choice anywhere.
  static List<Color> gradientFor(String seed) {
    final index = seed.hashCode.abs() % cardGradients.length;
    return cardGradients[index];
  }
}

/// The warm paper palette used by the score/practice surface and its
/// controls. These are the exact tones that were previously re-declared as
/// local `const` blocks inside main.dart's build methods — naming them once
/// here is what keeps the drawer, the pen panel and the tool buttons from
/// drifting apart when one of them is edited.
abstract final class PracticePalette {
  static const Color ivory = Color(0xFFF7F2E7);
  static const Color paper = Color(0xFFFFFCF4);
  static const Color brown = Color(0xFF30271F);
  static const Color mutedBrown = Color(0xFF75695B);
  static const Color gold = Color(0xFF9A7A2C);
  static const Color lightGold = Color(0xFFD8C58D);

  /// Used for the off-pitch verdict and the live-recording state.
  static const Color alert = Color(0xFFB2564B);

  static const List<Color> penColors = [
    gold,
    brown,
    Color(0xFF5B7188), // muted blue
    Color(0xFF62765B), // muted green
    Color(0xFFB1844D), // warm amber
  ];
}

/// The dark turntable surface: the navigator, the boot splash, and the
/// disks themselves. Separate from [PracticePalette] on purpose — the
/// navigator is deliberately a dark room the lit pages open out of.
abstract final class TurntablePalette {
  static const Color background = Color(0xFF1B1B1F);
  static const Color mat = Color(0xFF232327);
  static const Color parchment = Color(0xFFEDE6DA);

  static const Color diskPractice = Color(0xFF0B0B0D);
  static const Color diskSearch = Color(0xFF16121A);
  static const Color diskShelf = Color(0xFF12140F);
  static const Color diskQuiz = Color(0xFF1A1016);

  static const Color tonearmMount = Color(0xFF2A2A2E);
  static const Color tonearmArm = Color(0xFFB9B9BD);
  static const Color tonearmHead = Color(0xFF1E1E22);
}

/// The recorder button's own neutrals, which sit on top of the score paper
/// rather than in either palette above.
abstract final class RecorderPalette {
  static const Color labelIdle = Color(0xFF77736B);
  static const Color labelActive = Color(0xFF4D4A45);
  static const Color haloIdle = Color(0xFF9A8F7E);
  static const Color icon = Color(0xFF5F5A52);
}
