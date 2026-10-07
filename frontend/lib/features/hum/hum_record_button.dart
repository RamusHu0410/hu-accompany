import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:hu_accomponist/features/hum/hum_controller.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// Hold to hum, let go to hear it. The label under the button says what is
/// happening, so there is never a silent wait.
class HumRecordButton extends StatelessWidget {
  const HumRecordButton({
    super.key,
    required this.phase,
    required this.onStart,
    required this.onStop,
  });

  final HumPhase phase;
  final VoidCallback onStart;
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    final recording = phase == HumPhase.recording;
    final busy = phase == HumPhase.analyzing || phase == HumPhase.making;
    final color = recording ? PracticePalette.alert : PracticePalette.gold;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        GestureDetector(
          onLongPressStart: busy
              ? null
              : (_) {
                  HapticFeedback.mediumImpact();
                  onStart();
                },
          onLongPressEnd: (_) => onStop(),
          onLongPressCancel: onStop,
          child: AnimatedContainer(
            duration: Motion.fast,
            width: recording ? 104 : 92,
            height: recording ? 104 : 92,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: busy ? PracticePalette.lightGold : color,
              boxShadow: [
                BoxShadow(
                  color: color.withValues(alpha: recording ? 0.45 : 0.25),
                  blurRadius: recording ? 28 : 14,
                  spreadRadius: recording ? 6 : 0,
                ),
              ],
            ),
            child: Center(
              child: busy
                  ? const SizedBox(
                      width: 28,
                      height: 28,
                      child: CircularProgressIndicator(
                        strokeWidth: 3,
                        color: PracticePalette.paper,
                      ),
                    )
                  : const Icon(
                      Icons.mic_rounded,
                      size: 40,
                      color: PracticePalette.paper,
                    ),
            ),
          ),
        ),
        const SizedBox(height: Space.sm),
        Text(
          _label,
          style: const TextStyle(
            color: PracticePalette.mutedBrown,
            fontSize: 13,
            letterSpacing: 0.4,
          ),
        ),
      ],
    );
  }

  String get _label => switch (phase) {
    HumPhase.idle => 'Hold to hum',
    HumPhase.recording => 'Listening... let go when you are done',
    HumPhase.analyzing => 'Finding your tune...',
    HumPhase.making => 'Making your song...',
  };
}
