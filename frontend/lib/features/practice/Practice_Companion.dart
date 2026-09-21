import 'dart:async';

import 'package:flutter/material.dart';

import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';
import 'package:hu_accomponist/integrations/feedback/Pull_back_phrase.dart';
import 'package:hu_accomponist/features/practice/Character_mood_display.dart';
import 'package:hu_accomponist/features/practice/Phrase_Feedback.dart';
import 'package:hu_accomponist/features/practice/Phrase_Feedback_Pill.dart';

/// Where the companion's three sprites live.
abstract final class CompanionSprites {
  static const String neutral = 'assets/images/Tsundere_Music.png';
  static const String pleased = 'assets/images/Tsundere_Music_Listen.png';
  static const String annoyed = 'assets/images/Tsundere_Music_Mad.png';
}

/// Corner-anchored practice companion: the tsundere sprite, plus the
/// feedback card for the phrase just analyzed.
///
/// Owns all of the presentation timing -- when the card appears, how long it
/// stays, when the sprite falls back to neutral -- so the score screen only
/// has to hand over the latest [PhraseReport] and forget about it. Pass
/// null for [report] to reset to the idle state.
///
/// Deliberately a leaf: it never rebuilds the score underneath it, and the
/// auto-dismiss timer lives here rather than in the page's state, so a
/// dismissal does not rebuild the whole practice screen.
class PracticeCompanion extends StatefulWidget {
  final PhraseReport? report;

  /// Hides the sprite while the player is mid-phrase, so she is not
  /// reacting to a performance that has not been judged yet.
  final bool isRecording;

  /// How long the card lingers before dismissing itself.
  final Duration linger;

  const PracticeCompanion({
    super.key,
    required this.report,
    required this.isRecording,
    this.linger = const Duration(seconds: 6),
  });

  @override
  State<PracticeCompanion> createState() => _PracticeCompanionState();
}

class _PracticeCompanionState extends State<PracticeCompanion> {
  Timer? _dismiss;
  PhraseReport? _visible;

  @override
  void initState() {
    super.initState();
    _visible = widget.report;
    _restartTimer();
  }

  @override
  void didUpdateWidget(PracticeCompanion old) {
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

  /// She settles back to neutral once the card is gone, so her mood tracks
  /// what is currently being shown rather than the last phrase forever.
  ///
  /// The band comes from [PhraseFeedback.forScore] rather than a local
  /// cutoff, so her expression always agrees with the recorder halo and the
  /// drawer's status row.
  String get _sprite {
    final report = _visible;
    if (report == null) return CompanionSprites.neutral;
    return switch (PhraseFeedback.forScore(report.scores.overall)) {
      PhraseFeedback.good => CompanionSprites.pleased,
      PhraseFeedback.fair => CompanionSprites.neutral,
      PhraseFeedback.off => CompanionSprites.annoyed,
      PhraseFeedback.none => CompanionSprites.neutral,
    };
  }

  @override
  Widget build(BuildContext context) {
    final report = _visible;

    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        AnimatedSwitcher(
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
        ),
        const SizedBox(height: Space.xs),
        // Fades out while recording instead of unmounting, so the sprite
        // does not pop back in at a different size when it returns.
        AnimatedOpacity(
          opacity: widget.isRecording ? 0.25 : 1,
          duration: Motion.slow,
          child: IgnorePointer(
            child: CharacterMoodDisplay(
              assetPath: _sprite,
              width: 92,
              height: 138,
            ),
          ),
        ),
      ],
    );
  }
}
