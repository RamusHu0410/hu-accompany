/// How the last analyzed phrase went.
///
/// [none] is the idle state — before any phrase has been judged, and
/// between recordings.
///
/// The three graded bands exist because a single pass/fail cutoff made the
/// companion swing between delighted and annoyed over a couple of points
/// either side of 80, which read as erratic rather than responsive. [fair]
/// is the middle band: played, not clean, nothing to celebrate or sulk about.
enum PhraseFeedback {
  none,
  good,
  fair,
  off;

  /// The one place these thresholds live. Everything that reacts to a
  /// phrase score — the companion's sprite, the recorder halo tint, the
  /// drawer status row, the feedback card's accent — goes through here, so
  /// they cannot drift apart or disagree about the same number.
  static const int goodAtOrAbove = 80;
  static const int fairAtOrAbove = 55;

  /// Maps a phase-1 `scores.overall` (0-100) onto a mood band.
  static PhraseFeedback forScore(int overall) {
    if (overall >= goodAtOrAbove) return PhraseFeedback.good;
    if (overall >= fairAtOrAbove) return PhraseFeedback.fair;
    return PhraseFeedback.off;
  }

  /// True for the bands worth drawing attention to in an accent colour.
  bool get isGraded => this != PhraseFeedback.none;
}
