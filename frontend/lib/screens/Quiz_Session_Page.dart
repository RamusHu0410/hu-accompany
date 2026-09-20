import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/Quiz_Question.dart';
import '../models/Quiz_Set.dart';
import '../theme/Design_Tokens.dart';
import '../widgets/Library_Browse.dart';
import '../widgets/Press_Scale.dart';
import '../widgets/Quiz_Chrome.dart';
import '../widgets/Quiz_Question_Card.dart';
import 'Quiz_Results_Page.dart';

/// Runs one quiz: shows a question at a time, records what was answered,
/// and hands a [QuizResult] to the results page at the end.
///
/// Answers are graded immediately so the student sees right/wrong before
/// moving on — that feedback is the point of a practice quiz. Grading
/// itself lives on [QuizQuestion.isCorrect] so this screen and the results
/// review cannot disagree.
class Quiz_Session_Page extends StatefulWidget {
  final QuizSet set;
  const Quiz_Session_Page({super.key, required this.set});

  @override
  State<Quiz_Session_Page> createState() => _Quiz_Session_PageState();
}

class _Quiz_Session_PageState extends State<Quiz_Session_Page> {
  final TextEditingController _typed = TextEditingController();
  final List<QuizAnswer> _answers = [];

  int _index = 0;

  /// Null until the current question has been committed; once set, the
  /// card switches to its reviewed state and the action button advances.
  String? _submitted;

  QuizQuestion get _question => widget.set.questions[_index];
  bool get _isLast => _index == widget.set.questions.length - 1;
  bool get _isReviewing => _submitted != null;

  @override
  void dispose() {
    _typed.dispose();
    super.dispose();
  }

  void _submit(String response) {
    if (_isReviewing) return;
    final correct = _question.isCorrect(response);
    // Distinguishable by feel, so the verdict lands before the eye reaches
    // the colour change.
    if (correct) {
      HapticFeedback.lightImpact();
    } else {
      HapticFeedback.mediumImpact();
    }
    setState(() {
      _submitted = response;
      _answers.add(QuizAnswer(question: _question, response: response));
    });
  }

  void _skip() {
    if (_isReviewing) return;
    HapticFeedback.selectionClick();
    setState(() {
      _submitted = '';
      _answers.add(QuizAnswer(question: _question, response: null));
    });
  }

  void _advance() {
    if (_isLast) {
      _finish();
      return;
    }
    setState(() {
      _index += 1;
      _submitted = null;
      _typed.clear();
    });
  }

  void _finish() {
    final result = QuizResult(set: widget.set, answers: _answers);
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => Quiz_Results_Page(result: result)),
    );
  }

  @override
  Widget build(BuildContext context) {
    return QuizScaffold(
      label: widget.set.levelLabel.toUpperCase(),
      title: 'Question ${_index + 1}',
      subtitle: widget.set.subtitle,
      child: Column(
        children: [
          const SizedBox(height: Space.md),
          _progress(),
          const SizedBox(height: Space.md),
          Expanded(
            child: ListView(
              physics: AppScroll.physics,
              padding: const EdgeInsets.only(bottom: Space.md),
              children: [
                QuizQuestionCard(
                  // Keyed by id so moving to the next question animates as
                  // a replacement rather than mutating the card in place.
                  key: ValueKey(_question.id),
                  question: _question,
                  submitted: _submitted,
                  controller: _typed,
                  onChoose: _submit,
                ),
              ],
            ),
          ),
          _actions(),
          const SizedBox(height: Space.md),
        ],
      ),
    );
  }

  Widget _progress() {
    final answered = _answers.length;
    final total = widget.set.questions.length;
    return Column(
      children: [
        ClipRRect(
          borderRadius: Radii.pillRadius,
          child: TweenAnimationBuilder<double>(
            tween: Tween(begin: 0, end: total == 0 ? 0 : answered / total),
            duration: Motion.slow,
            curve: Motion.enter,
            builder: (context, value, _) => LinearProgressIndicator(
              value: value,
              minHeight: 4,
              backgroundColor: libInk.withValues(alpha: 0.08),
              valueColor: const AlwaysStoppedAnimation(libGold),
            ),
          ),
        ),
        const SizedBox(height: Space.xs),
        Text(
          '${_index + 1} of $total',
          style: TextStyle(
            fontFamily: libBookFont,
            fontFamilyFallback: libBookFontFallback,
            fontSize: 11,
            letterSpacing: 1,
            color: libInk.withValues(alpha: 0.45),
          ),
        ),
      ],
    );
  }

  Widget _actions() {
    if (_isReviewing) {
      return _primaryButton(
        label: _isLast ? 'See results' : 'Next question',
        onTap: _advance,
      );
    }

    // Fill-in-the-blank needs its own commit action; multiple choice
    // commits on the tapped option itself.
    if (_question.kind == QuizKind.fillBlank) {
      return Row(
        children: [
          Expanded(
            child: _primaryButton(
              label: 'Check answer',
              onTap: () => _submit(_typed.text),
            ),
          ),
          const SizedBox(width: Space.sm),
          _skipButton(),
        ],
      );
    }

    return Row(
      children: [
        Expanded(
          child: Text(
            'Choose an answer',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: libBookFont,
              fontFamilyFallback: libBookFontFallback,
              fontStyle: FontStyle.italic,
              fontSize: 13,
              color: libInk.withValues(alpha: 0.45),
            ),
          ),
        ),
        _skipButton(),
      ],
    );
  }

  Widget _skipButton() {
    return PressScale(
      onTap: _skip,
      borderRadius: Radii.pillRadius,
      child: Container(
        height: 52,
        padding: const EdgeInsets.symmetric(horizontal: Space.lg),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          borderRadius: Radii.pillRadius,
          border: Border.all(color: libInk.withValues(alpha: 0.16)),
        ),
        child: Text(
          'Skip',
          style: TextStyle(
            fontFamily: libBookFont,
            fontFamilyFallback: libBookFontFallback,
            fontSize: 14,
            color: libInk.withValues(alpha: 0.6),
          ),
        ),
      ),
    );
  }

  Widget _primaryButton({required String label, required VoidCallback onTap}) {
    return PressScale(
      onTap: onTap,
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
        child: Text(
          label,
          style: const TextStyle(
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
