import 'package:flutter/material.dart';

import 'package:hu_accomponist/features/quiz/Quiz_Question.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';
import 'package:hu_accomponist/features/search/Library_Browse.dart';
import 'package:hu_accomponist/shared/ui/Press_Scale.dart';

/// Verdict colours. Green and red are the only two tones in the quiz that
/// sit outside the library's cream/gold palette — correctness has to be
/// legible at a glance, and gold alone cannot carry both states.
const Color quizCorrect = Color(0xFF3E6B4F);
const Color quizWrong = Color(0xFFA34A42);

/// Renders one question: its prompt, and either a list of choices or a
/// fill-in-the-blank field.
///
/// Stateless — [submitted] being non-null is what flips it into the
/// reviewed state, so the session page remains the single owner of what has
/// been answered.
class QuizQuestionCard extends StatelessWidget {
  final QuizQuestion question;

  /// Null while unanswered. Empty string means the question was skipped.
  final String? submitted;

  final TextEditingController controller;
  final ValueChanged<String> onChoose;

  const QuizQuestionCard({
    super.key,
    required this.question,
    required this.submitted,
    required this.controller,
    required this.onChoose,
  });

  bool get _reviewing => submitted != null;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(Space.lg),
      decoration: BoxDecoration(
        color: libCreamCard,
        borderRadius: Radii.modalRadius,
        border: Border.all(color: libInk.withValues(alpha: 0.10)),
        boxShadow: Elevations.card(Colors.black),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _tags(),
          const SizedBox(height: Space.sm),
          Text(
            question.prompt,
            style: const TextStyle(
              fontFamily: libBookFont,
              fontFamilyFallback: libBookFontFallback,
              fontSize: 17,
              height: 1.4,
              fontWeight: FontWeight.w600,
              color: libInk,
            ),
          ),
          const SizedBox(height: Space.md),
          if (question.kind == QuizKind.multipleChoice)
            ...question.choices.map(_choice)
          else
            _blank(),
          if (_reviewing) ...[
            const SizedBox(height: Space.md),
            _explanation(),
          ],
        ],
      ),
    );
  }

  Widget _tags() {
    return Row(
      children: [
        _tag(question.category.toUpperCase(), libGold),
        if (question.isAdvanced) ...[
          const SizedBox(width: Space.xs),
          _tag('ARCT', libInk.withValues(alpha: 0.45)),
        ],
      ],
    );
  }

  Widget _tag(String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: Space.xs,
        vertical: Space.xxs / 2,
      ),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: Radii.pillRadius,
      ),
      child: Text(
        text,
        style: TextStyle(
          fontFamily: libBookFont,
          fontFamilyFallback: libBookFontFallback,
          fontSize: 9,
          fontWeight: FontWeight.w700,
          letterSpacing: 1.2,
          color: color,
        ),
      ),
    );
  }

  Widget _choice(String choice) {
    final isAnswer = choice == question.answer;
    final isPicked = _reviewing && choice == submitted;

    // Before answering every option is neutral. After, the correct one is
    // always marked — including when the student picked something else, so
    // a wrong answer still teaches the right one.
    Color border = libInk.withValues(alpha: 0.12);
    Color fill = libCream;
    Color text = libInk;
    if (_reviewing && isAnswer) {
      border = quizCorrect;
      fill = quizCorrect.withValues(alpha: 0.10);
      text = quizCorrect;
    } else if (isPicked) {
      border = quizWrong;
      fill = quizWrong.withValues(alpha: 0.10);
      text = quizWrong;
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: Space.xs),
      child: PressScale(
        onTap: _reviewing ? null : () => onChoose(choice),
        borderRadius: Radii.cardRadius,
        pressedScale: 0.98,
        child: AnimatedContainer(
          duration: Motion.fast,
          curve: Motion.standard,
          padding: const EdgeInsets.symmetric(
            horizontal: Space.sm,
            vertical: Space.sm,
          ),
          decoration: BoxDecoration(
            color: fill,
            borderRadius: Radii.cardRadius,
            border: Border.all(color: border),
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  choice,
                  style: TextStyle(
                    fontFamily: libBookFont,
                    fontFamilyFallback: libBookFontFallback,
                    fontSize: 14,
                    height: 1.3,
                    color: text,
                  ),
                ),
              ),
              if (_reviewing && (isAnswer || isPicked)) ...[
                const SizedBox(width: Space.xs),
                Icon(
                  isAnswer ? Icons.check_rounded : Icons.close_rounded,
                  size: 16,
                  color: text,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _blank() {
    final correct = _reviewing && question.isCorrect(submitted);
    final border = !_reviewing
        ? libInk.withValues(alpha: 0.14)
        : (correct ? quizCorrect : quizWrong);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: Space.sm),
          decoration: BoxDecoration(
            color: libCream,
            borderRadius: Radii.cardRadius,
            border: Border.all(color: border),
          ),
          child: TextField(
            controller: controller,
            enabled: !_reviewing,
            textInputAction: TextInputAction.done,
            onSubmitted: _reviewing ? null : onChoose,
            style: const TextStyle(
              fontFamily: libBookFont,
              fontFamilyFallback: libBookFontFallback,
              fontSize: 15,
              color: libInk,
            ),
            decoration: InputDecoration(
              border: InputBorder.none,
              hintText: 'Type your answer',
              hintStyle: TextStyle(
                fontFamily: libBookFont,
                fontFamilyFallback: libBookFontFallback,
                fontStyle: FontStyle.italic,
                fontSize: 14,
                color: libInk.withValues(alpha: 0.3),
              ),
            ),
            cursorColor: libGold,
          ),
        ),
        if (_reviewing && !correct) ...[
          const SizedBox(height: Space.xs),
          Text(
            'Answer: ${question.answer}',
            style: const TextStyle(
              fontFamily: libBookFont,
              fontFamilyFallback: libBookFontFallback,
              fontSize: 13,
              fontWeight: FontWeight.w700,
              color: quizCorrect,
            ),
          ),
        ],
      ],
    );
  }

  Widget _explanation() {
    return Container(
      padding: const EdgeInsets.all(Space.sm),
      decoration: BoxDecoration(
        color: libInk.withValues(alpha: 0.04),
        borderRadius: Radii.cardRadius,
      ),
      child: Text(
        question.explanation,
        style: TextStyle(
          fontFamily: libBookFont,
          fontFamilyFallback: libBookFontFallback,
          fontSize: 13,
          height: 1.45,
          color: libInk.withValues(alpha: 0.75),
        ),
      ),
    );
  }
}
