import 'package:flutter/material.dart';

/// The 8pt spacing grid. Values below 8 are the 4pt half-step used for
/// tight optical pairs (a label and the line under it), never for layout
/// gaps — keeping those on the half-step is what stops arbitrary 7s, 9s
/// and 11s from creeping back in.
abstract final class Space {
  static const double xxs = 4;
  static const double xs = 8;
  static const double sm = 12;
  static const double md = 16;
  static const double lg = 20;
  static const double xl = 24;
  static const double xxl = 32;
  static const double xxxl = 40;
}

/// Corner radii. Cards and modals share [card]/[modal] so a tile never
/// reads as a different family than the sheet it opens into.
abstract final class Radii {
  static const double xs = 4;
  static const double sm = 8;
  static const double card = 12;
  static const double lg = 16;
  static const double modal = 20;
  static const double pill = 999;

  static const BorderRadius cardRadius = BorderRadius.all(
    Radius.circular(card),
  );
  static const BorderRadius lgRadius = BorderRadius.all(Radius.circular(lg));
  static const BorderRadius modalRadius = BorderRadius.all(
    Radius.circular(modal),
  );
  static const BorderRadius pillRadius = BorderRadius.all(
    Radius.circular(pill),
  );
}

/// Animation timings. Everything user-initiated stays at or under 300ms so
/// the app reads as snappy rather than showy; [page] is the only longer
/// one because a route transition covers a full-screen change.
abstract final class Motion {
  static const Duration press = Duration(milliseconds: 120);
  static const Duration fast = Duration(milliseconds: 180);
  static const Duration base = Duration(milliseconds: 240);
  static const Duration slow = Duration(milliseconds: 300);
  static const Duration page = Duration(milliseconds: 320);

  /// Decelerating — for things entering or settling into place.
  static const Curve enter = Curves.easeOutCubic;

  /// Accelerating — for things leaving.
  static const Curve exit = Curves.easeInCubic;

  /// Symmetric — for state swaps that neither enter nor leave.
  static const Curve standard = Curves.easeInOut;
}

/// Card and overlay shadows, in one place so depth stays consistent
/// between a shelf tile, a result row and a floating panel.
abstract final class Elevations {
  static List<BoxShadow> card(Color shadow) => [
    BoxShadow(
      color: shadow.withValues(alpha: 0.06),
      blurRadius: 8,
      offset: const Offset(0, 2),
    ),
  ];

  static List<BoxShadow> raised(Color shadow) => [
    BoxShadow(
      color: shadow.withValues(alpha: 0.10),
      blurRadius: 12,
      offset: const Offset(0, 4),
    ),
  ];

  static List<BoxShadow> overlay(Color shadow) => [
    BoxShadow(
      color: shadow.withValues(alpha: 0.14),
      blurRadius: 20,
      offset: const Offset(0, 8),
    ),
  ];
}

/// Scroll behaviour shared by every list in the app, so the shelf grid and
/// the library results decelerate identically instead of one clamping and
/// the other bouncing depending on which platform default applied.
abstract final class AppScroll {
  static const ScrollPhysics physics = BouncingScrollPhysics(
    decelerationRate: ScrollDecelerationRate.fast,
    parent: AlwaysScrollableScrollPhysics(),
  );
}
