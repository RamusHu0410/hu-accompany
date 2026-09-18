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
