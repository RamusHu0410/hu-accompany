import 'dart:async';

import 'package:flutter/material.dart';

import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';
import 'package:hu_accomponist/integrations/feedback/Pull_back_phrase.dart';
import 'package:hu_accomponist/features/practice/Phrase_Feedback_Pill.dart';

/// Corner-anchored feedback card for the phrase just analyzed.
///
/// Owns all of the presentation timing -- when the card appears and how
/// long it stays -- so the score screen only has to hand over the latest
/// [PhraseReport] and forget about it. Pass null for [report] to reset to
/// the idle state.
///
/// Deliberately a leaf: it never rebuilds the score underneath it, and the
/// auto-dismiss timer lives here rather than in the page's state, so a
/// dismissal does not rebuild the whole practice screen.
class PhraseFeedbackOverlay extends StatefulWidget {
  final PhraseReport? report;

  /// How long the card lingers before dismissing itself.
  final Duration linger;

  const PhraseFeedbackOverlay({
    super.key,
    required this.report,
    this.linger = const Duration(seconds: 6),
  });

  @override
  State<PhraseFeedbackOverlay> createState() => _PhraseFeedbackOverlayState();
}

class _PhraseFeedbackOverlayState extends State<PhraseFeedbackOverlay> {
  Timer? _dismiss;
  PhraseReport? _visible;

  @override
  void initState() {
    super.initState();
    _visible = widget.report;
    _restartTimer();
  }

  @override
  void didUpdateWidget(PhraseFeedbackOverlay old) {
    super.didUpdateWidget(old);
    if (!identical(old.report, widget.report)) {
      // A new phrase arriving replaces whatever is on screen and restarts
      // the clock, rather than queueing behind the previous card.
      setState(() => _visible = widget.report);
      _restartTimer();
    }
  }

  void _restartTimer() {
    _dismiss?.cancel();
    if (_visible == null) return;
    _dismiss = Timer(widget.linger, () {
      if (mounted) setState(() => _visible = null);
    });
  }

  void _dismissNow() {
    _dismiss?.cancel();
    setState(() => _visible = null);
  }

  @override
  void dispose() {
    _dismiss?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final report = _visible;

    return AnimatedSwitcher(
      duration: Motion.slow,
      switchInCurve: Motion.enter,
      switchOutCurve: Motion.exit,
      transitionBuilder: (child, animation) => FadeTransition(
        opacity: animation,
        child: SlideTransition(
          position: Tween<Offset>(
            begin: const Offset(0.12, 0),
            end: Offset.zero,
          ).animate(animation),
          child: child,
        ),
      ),
      child: report == null
          ? const SizedBox(key: ValueKey('no-feedback'), width: 268)
          : PhraseFeedbackPill(
              key: ValueKey(report.phrase),
              report: report,
              onDismiss: _dismissNow,
            ),
    );
  }
}
