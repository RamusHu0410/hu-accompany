import 'package:flutter/material.dart';

import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';
import 'package:hu_accomponist/integrations/feedback/Pull_back_phrase.dart';
import 'package:hu_accomponist/features/practice/Phrase_Feedback.dart';
import 'package:hu_accomponist/features/practice/Practice_Settings_Drawer.dart';

/// Compact result card shown after each analyzed phrase.
///
/// Reads the phase-1 shape documented in backend/feedback_generator's
/// README: an `overall` 0-100 plus per-dimension scores that may be null,
/// and a `feedback` list of findings carrying category, severity and a
/// message.
///
/// Null dimensions are omitted rather than drawn as zero. That distinction
/// is load-bearing -- `dynamics` and `pedaling` are *always* null because
/// nothing upstream carries loudness or pedal events, so showing them as 0
/// would report a failure the player did not commit.
class PhraseFeedbackPill extends StatelessWidget {
  final PhraseReport report;
  final VoidCallback onDismiss;

  const PhraseFeedbackPill({
    super.key,
    required this.report,
    required this.onDismiss,
  });

  PhraseFeedback get _band =>
      PhraseFeedback.forScore(report.scores.overall);

  bool get _isGood => _band == PhraseFeedback.good;

  /// Same source of truth as the companion and the recorder halo.
  Color get _accent => PracticeSettingsDrawer.feedbackColor(_band);

  /// How many findings a card this size can carry without covering the
  /// score. Anything beyond this is counted in a trailing line rather than
  /// dropped silently.
  static const int _maxShown = 3;

  /// Findings worst-first: major before minor, then most confident first.
  List<PhraseFeedbackItem> get _ranked {
    final sorted = [...report.feedback]..sort((a, b) {
      final severity = _weight(b.severity).compareTo(_weight(a.severity));
      if (severity != 0) return severity;
      return b.confidence.compareTo(a.confidence);
    });
    return sorted;
  }

  static int _weight(String severity) => severity == 'major' ? 2 : 1;

  @override
  Widget build(BuildContext context) {
    final ranked = _ranked;
    final shown = ranked.take(_maxShown).toList();
    final hidden = ranked.length - shown.length;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onDismiss,
        borderRadius: Radii.lgRadius,
        child: Container(
          width: 268,
          padding: const EdgeInsets.all(Space.sm),
          decoration: BoxDecoration(
            color: PracticePalette.paper,
            borderRadius: Radii.lgRadius,
            border: Border.all(color: _accent.withValues(alpha: 0.45)),
            boxShadow: Elevations.overlay(PracticePalette.brown),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _header(),
              const SizedBox(height: Space.xs),
              _dimensions(),
              for (final item in shown) ...[
                const SizedBox(height: Space.xs),
                _finding(item),
              ],
              if (hidden > 0) ...[
                const SizedBox(height: Space.xxs),
                Text(
                  '+$hidden more',
                  style: TextStyle(
                    color: PracticePalette.mutedBrown.withValues(alpha: 0.8),
                    fontSize: 10,
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _header() {
    return Row(
      children: [
        Icon(
          _isGood ? Icons.check_circle_rounded : Icons.error_outline_rounded,
          size: 16,
          color: _accent,
        ),
        const SizedBox(width: Space.xs),
        Expanded(
          child: Text(
            'Phrase ${report.phrase}',
            style: const TextStyle(
              color: PracticePalette.brown,
              fontSize: 13,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.3,
            ),
          ),
        ),
        Text(
          '${report.scores.overall}',
          style: TextStyle(
            color: _accent,
            fontSize: 20,
            fontWeight: FontWeight.w700,
            height: 1,
          ),
        ),
      ],
    );
  }

  /// One chip per dimension the backend actually scored.
  Widget _dimensions() {
    final scores = report.scores;
    final entries = <({String label, int? value})>[
      (label: 'Pitch', value: scores.pitch),
      (label: 'Rhythm', value: scores.rhythm),
      (label: 'Tempo', value: scores.tempo),
      (label: 'Artic.', value: scores.articulation),
      (label: 'Notes', value: scores.notes),
    ].where((e) => e.value != null).toList();

    if (entries.isEmpty) return const SizedBox.shrink();

    return Wrap(
      spacing: Space.xxs,
      runSpacing: Space.xxs,
      children: entries
          .map((e) => _chip(e.label, e.value!))
          .toList(growable: false),
    );
  }

  Widget _chip(String label, int value) {
    // Graded through the same bands as the headline, so a chip never
    // contradicts the overall verdict beside it.
    final tint = PracticeSettingsDrawer.feedbackColor(
      PhraseFeedback.forScore(value),
    );
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: Space.xs,
        vertical: Space.xxs / 2,
      ),
      decoration: BoxDecoration(
        color: tint.withValues(alpha: 0.10),
        borderRadius: Radii.pillRadius,
      ),
      child: Text(
        '$label $value',
        style: TextStyle(
          color: tint,
          fontSize: 10,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.2,
        ),
      ),
    );
  }

  Widget _finding(PhraseFeedbackItem item) {
    return Container(
      padding: const EdgeInsets.all(Space.xs),
      decoration: BoxDecoration(
        color: PracticePalette.brown.withValues(alpha: 0.04),
        borderRadius: Radii.cardRadius,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            margin: const EdgeInsets.only(top: 3),
            width: 5,
            height: 5,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: item.severity == 'major'
                  ? PracticePalette.alert
                  : PracticePalette.mutedBrown,
            ),
          ),
          const SizedBox(width: Space.xs),
          Expanded(
            child: Text(
              'Bar ${item.bars} · ${item.message}',
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: PracticePalette.mutedBrown,
                fontSize: 11,
                height: 1.35,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
