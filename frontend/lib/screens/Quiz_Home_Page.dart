import 'package:flutter/material.dart';

import '../models/Quiz_Set.dart';
import '../services/Quiz_Generator.dart';
import '../theme/Design_Tokens.dart';
import '../widgets/Library_Browse.dart';
import '../widgets/Press_Scale.dart';
import '../widgets/Quiz_Chrome.dart';
import 'Quiz_Session_Page.dart';

/// Entry point for the quiz feature: type a topic heading, get a quiz.
///
/// The input is deliberately free text rather than a picker. Students
/// already have a heading at the top of their cheat sheet, and the backend
/// parses it, so pasting that line in is less work than hunting through a
/// dropdown — while a bare "baroque" still resolves.
class Quiz_Home_Page extends StatefulWidget {
  const Quiz_Home_Page({super.key});

  @override
  State<Quiz_Home_Page> createState() => _Quiz_Home_PageState();
}

class _Quiz_Home_PageState extends State<Quiz_Home_Page> {
  final TextEditingController _topic = TextEditingController();

  bool _loading = false;
  String? _error;
  int _length = 15;

  static const List<int> _lengthOptions = [10, 15, 20, 30];

  static const List<String> _examples = [
    'The Middle Ages (ad 476 - ad 1450)',
    'The Renaissance',
    'The Baroque Era',
    'The Classical Era',
    'The Romantic Era',
    'The Twentieth Century',
  ];

  @override
  void dispose() {
    _topic.dispose();
    super.dispose();
  }

  Future<void> _start() async {
    final topic = _topic.text.trim();
    if (topic.isEmpty) {
      setState(() => _error = 'Type a topic to build a quiz from.');
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final set = await QuizGenerator.generate(topic, length: _length);
      if (!mounted) return;
      setState(() => _loading = false);
      final result = await Navigator.of(context).push<QuizResult>(
        MaterialPageRoute(builder: (_) => Quiz_Session_Page(set: set)),
      );
      // A finished run pops back here with its result; nothing to do with
      // it at this level, but this is where a future "save to shelf" would
      // hook in.
      if (result != null) debugPrint('quiz finished: ${result.percent}%');
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = _friendly(e);
      });
    }
  }

  String _friendly(Object e) {
    final msg = e.toString();
    return msg.startsWith('Exception: ') ? msg.substring(11) : msg;
  }

  @override
  Widget build(BuildContext context) {
    return QuizScaffold(
      label: 'MUSIC THEORY & HISTORY',
      title: 'The Quiz',
      child: ListView(
        physics: AppScroll.physics,
        padding: const EdgeInsets.only(bottom: Space.xxl),
        children: [
          const SizedBox(height: Space.xl),
          const QuizSectionLabel('Topic'),
          const SizedBox(height: Space.sm),
          _input(),
          const SizedBox(height: Space.lg),
          const QuizSectionLabel('Questions'),
          const SizedBox(height: Space.sm),
          _lengthRow(),
          const SizedBox(height: Space.lg),
          const QuizSectionLabel('Try one of these'),
          const SizedBox(height: Space.sm),
          _exampleChips(),
          const SizedBox(height: Space.xl),
          if (_error != null) ...[
            QuizNotice(message: _error!),
            const SizedBox(height: Space.md),
          ],
          _startButton(),
        ],
      ),
    );
  }

  Widget _input() {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: Space.md,
        vertical: Space.xs,
      ),
      decoration: BoxDecoration(
        color: libCreamCard,
        borderRadius: Radii.modalRadius,
        border: Border.all(color: libInk.withValues(alpha: 0.14)),
        boxShadow: Elevations.card(Colors.black),
      ),
      child: TextField(
        controller: _topic,
        maxLines: 3,
        minLines: 2,
        textCapitalization: TextCapitalization.sentences,
        style: const TextStyle(
          fontFamily: libBookFont,
          fontFamilyFallback: libBookFontFallback,
          fontSize: 15,
          height: 1.4,
          color: libInk,
        ),
        decoration: InputDecoration(
          border: InputBorder.none,
          isDense: true,
          hintText: 'RCM HISTORY 10 + ARCT CHEAT SHEET\n'
              'The Middle Ages (ad 476 - ad 1450)',
          hintStyle: TextStyle(
            fontFamily: libBookFont,
            fontFamilyFallback: libBookFontFallback,
            fontStyle: FontStyle.italic,
            fontSize: 14,
            height: 1.4,
            color: libInk.withValues(alpha: 0.32),
          ),
        ),
        cursorColor: libGold,
      ),
    );
  }

  Widget _lengthRow() {
    return Row(
      children: _lengthOptions.map((count) {
        final selected = count == _length;
        return Expanded(
          child: Padding(
            padding: const EdgeInsets.only(right: Space.xs),
            child: PressScale(
              onTap: () => setState(() => _length = count),
              borderRadius: Radii.lgRadius,
              pressedScale: 0.95,
              child: AnimatedContainer(
                duration: Motion.fast,
                curve: Motion.standard,
                padding: const EdgeInsets.symmetric(vertical: Space.sm),
                decoration: BoxDecoration(
                  color: selected
                      ? libGold.withValues(alpha: 0.12)
                      : libCreamCard,
                  borderRadius: Radii.lgRadius,
                  border: Border.all(
                    color: selected
                        ? libGold
                        : libInk.withValues(alpha: 0.10),
                  ),
                ),
                child: Text(
                  '$count',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontFamily: libBookFont,
                    fontFamilyFallback: libBookFontFallback,
                    fontSize: 14,
                    fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                    color: selected ? libGold : libInk.withValues(alpha: 0.6),
                  ),
                ),
              ),
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _exampleChips() {
    return Wrap(
      spacing: Space.xs,
      runSpacing: Space.xs,
      children: _examples.map((example) {
        return PressScale(
          onTap: () => setState(() {
            _topic.text = 'RCM HISTORY 10 + ARCT CHEAT SHEET\n$example';
            _error = null;
          }),
          borderRadius: Radii.pillRadius,
          pressedScale: 0.94,
          child: Container(
            padding: const EdgeInsets.symmetric(
              horizontal: Space.sm,
              vertical: Space.xs,
            ),
            decoration: BoxDecoration(
              color: libCreamCard,
              borderRadius: Radii.pillRadius,
              border: Border.all(color: libInk.withValues(alpha: 0.12)),
            ),
            child: Text(
              example,
              style: TextStyle(
                fontFamily: libBookFont,
                fontFamilyFallback: libBookFontFallback,
                fontSize: 12,
                color: libInk.withValues(alpha: 0.7),
              ),
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _startButton() {
    return PressScale(
      onTap: _loading ? null : _start,
      borderRadius: Radii.pillRadius,
      haptic: PressHaptic.medium,
      pressedScale: 0.98,
      child: AnimatedContainer(
        duration: Motion.fast,
        height: 52,
        decoration: BoxDecoration(
          color: _loading ? libGold.withValues(alpha: 0.5) : libGold,
          borderRadius: Radii.pillRadius,
          boxShadow: Elevations.raised(Colors.black),
        ),
        alignment: Alignment.center,
        child: _loading
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: libCream,
                ),
              )
            : const Text(
                'Begin quiz',
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
