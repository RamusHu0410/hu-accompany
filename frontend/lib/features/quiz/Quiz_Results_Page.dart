import 'package:flutter/material.dart';

import 'package:hu_accomponist/features/quiz/Quiz_Question.dart';
import 'package:hu_accomponist/features/quiz/Quiz_Set.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';
import 'package:hu_accomponist/features/search/Library_Browse.dart';
import 'package:hu_accomponist/shared/ui/Press_Scale.dart';
import 'package:hu_accomponist/features/quiz/Quiz_Chrome.dart';
import 'package:hu_accomponist/features/quiz/Quiz_Question_Card.dart' show quizCorrect, quizWrong;

/// Score summary plus a review of everything that was missed.
///
/// The review lists wrong *and* skipped answers together, since both are
/// gaps the student needs to see, and each carries the explanation from the
/// question bank so the page is useful without going back to the source.
class Quiz_Results_Page extends StatelessWidget {
  final QuizResult result;
  const Quiz_Results_Page({super.key, required this.result});

  @override
  Widget build(BuildContext context) {
    final missed = result.missed;

    return QuizScaffold(
      label: result.set.levelLabel.toUpperCase(),
      title: 'Results',
      subtitle: result.set.subtitle,
      child: ListView(
        physics: AppScroll.physics,
        padding: const EdgeInsets.only(bottom: Space.xxl),
        children: [
          const SizedBox(height: Space.lg),
          _scoreCard(),
          const SizedBox(height: Space.lg),
          const QuizSectionLabel('By category'),
          const SizedBox(height: Space.sm),
          ..._categoryRows(),
          const SizedBox(height: Space.lg),
          if (missed.isEmpty)
            const QuizNotice(
              message: 'Every question correct. Nothing to review.',
            )
          else ...[
            QuizSectionLabel('Review · ${missed.length}'),
            const SizedBox(height: Space.sm),
            ...missed.map(_reviewCard),
          ],
          const SizedBox(height: Space.lg),
          _doneButton(context),
        ],
      ),
    );
  }

  Widget _scoreCard() {
    return Container(
      padding: const EdgeInsets.all(Space.lg),
      decoration: BoxDecoration(
        color: libCreamCard,
        borderRadius: Radii.modalRadius,
        border: Border.all(color: libInk.withValues(alpha: 0.10)),
        boxShadow: Elevations.card(Colors.black),
      ),
      child: Column(
        children: [
          // Counts up from zero so the number lands rather than appearing.
          TweenAnimationBuilder<double>(
            tween: Tween(begin: 0, end: result.percent.toDouble()),
            duration: Motion.page,
            curve: Motion.enter,
            builder: (context, value, _) => Text(
              '${value.round()}%',
              style: const TextStyle(
                fontFamily: libBookFont,
                fontFamilyFallback: libBookFontFallback,
                fontSize: 48,
                fontWeight: FontWeight.w700,
                color: libInk,
              ),
            ),
          ),
          const SizedBox(height: Space.xxs),
          Text(
            '${result.correct} of ${result.total} correct',
            style: TextStyle(
              fontFamily: libBookFont,
              fontFamilyFallback: libBookFontFallback,
              fontSize: 14,
              color: libInk.withValues(alpha: 0.6),
            ),
          ),
          const SizedBox(height: Space.md),
          Row(
            children: [
              // Equal thirds rather than intrinsic widths: at phone width
              // the three labels plus their padding overflow the card.
              Expanded(child: _tally('Correct', result.correct, quizCorrect)),
              Expanded(child: _tally('Wrong', result.wrong, quizWrong)),
              Expanded(
                child: _tally(
                  'Skipped',
                  result.skipped,
                  libInk.withValues(alpha: 0.5),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _tally(String label, int value, Color color) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Space.xxs),
      child: Column(
        children: [
          Text(
            '$value',
            style: TextStyle(
              fontFamily: libBookFont,
              fontFamilyFallback: libBookFontFallback,
              fontSize: 20,
              fontWeight: FontWeight.w700,
              color: color,
            ),
          ),
          const SizedBox(height: Space.xxs / 2),
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontFamily: libBookFont,
              fontFamilyFallback: libBookFontFallback,
              fontSize: 11,
              letterSpacing: 0.5,
              color: libInk.withValues(alpha: 0.45),
            ),
          ),
        ],
      ),
    );
  }

  List<Widget> _categoryRows() {
    final tallies = result.byCategory.entries.toList()
      ..sort((a, b) => a.key.compareTo(b.key));

    return tallies.map((entry) {
      final ratio = entry.value.total == 0
          ? 0.0
          : entry.value.correct / entry.value.total;
      return Padding(
        padding: const EdgeInsets.only(bottom: Space.sm),
        child: Row(
          children: [
            SizedBox(
              width: 96,
              child: Text(
                entry.key,
                style: TextStyle(
                  fontFamily: libBookFont,
                  fontFamilyFallback: libBookFontFallback,
                  fontSize: 13,
                  color: libInk.withValues(alpha: 0.7),
                ),
              ),
            ),
            Expanded(
              child: ClipRRect(
                borderRadius: Radii.pillRadius,
                child: TweenAnimationBuilder<double>(
                  tween: Tween(begin: 0, end: ratio),
                  duration: Motion.page,
                  curve: Motion.enter,
                  builder: (context, value, _) => LinearProgressIndicator(
                    value: value,
                    minHeight: 6,
                    backgroundColor: libInk.withValues(alpha: 0.08),
                    valueColor: const AlwaysStoppedAnimation(libGold),
                  ),
                ),
              ),
            ),
            const SizedBox(width: Space.sm),
            Text(
              '${entry.value.correct}/${entry.value.total}',
              style: TextStyle(
                fontFamily: libBookFont,
                fontFamilyFallback: libBookFontFallback,
                fontSize: 12,
                color: libInk.withValues(alpha: 0.5),
              ),
            ),
          ],
        ),
      );
    }).toList();
  }

  Widget _reviewCard(QuizAnswer answer) {
    final question = answer.question;
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.sm),
      child: Container(
        padding: const EdgeInsets.all(Space.md),
        decoration: BoxDecoration(
          color: libCreamCard,
          borderRadius: Radii.modalRadius,
          border: Border.all(color: libInk.withValues(alpha: 0.10)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              question.prompt,
              style: const TextStyle(
                fontFamily: libBookFont,
                fontFamilyFallback: libBookFontFallback,
                fontSize: 14,
                height: 1.35,
                fontWeight: FontWeight.w600,
                color: libInk,
              ),
            ),
            const SizedBox(height: Space.xs),
            _line(
              answer.wasSkipped ? 'Skipped' : 'You said: ${answer.response}',
              quizWrong,
              answer.wasSkipped ? Icons.remove_rounded : Icons.close_rounded,
            ),
            const SizedBox(height: Space.xxs),
            _line(question.answer, quizCorrect, Icons.check_rounded),
            const SizedBox(height: Space.xs),
            Text(
              question.explanation,
              style: TextStyle(
                fontFamily: libBookFont,
                fontFamilyFallback: libBookFontFallback,
                fontSize: 12.5,
                height: 1.45,
                color: libInk.withValues(alpha: 0.7),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _line(String text, Color color, IconData icon) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 14, color: color),
        const SizedBox(width: Space.xs),
        Expanded(
          child: Text(
            text,
            style: TextStyle(
              fontFamily: libBookFont,
              fontFamilyFallback: libBookFontFallback,
              fontSize: 13,
              height: 1.3,
              color: color,
            ),
          ),
        ),
      ],
    );
  }

  Widget _doneButton(BuildContext context) {
    return PressScale(
      onTap: () => Navigator.of(context).maybePop(),
      borderRadius: Radii.pillRadius,
      haptic: PressHaptic.medium,
      pressedScale: 0.98,
      child: Container(
        height: 52,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: libGold,
          borderRadius: Radii.pillRadius,
          boxShadow: Elevations.raised(Colors.black),
        ),
        child: const Text(
          'Done',
          style: TextStyle(
            fontFamily: libBookFont,
            fontFamilyFallback: libBookFontFallback,
            fontSize: 16,
            fontWeight: FontWeight.w700,
            letterSpacing: 0.4,
            color: libCream,
          ),
        ),
      ),
    );
  }
}
