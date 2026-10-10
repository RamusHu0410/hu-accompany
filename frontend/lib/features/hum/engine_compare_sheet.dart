import 'package:flutter/material.dart';

import 'package:hu_accomponist/features/hum/engine_guide.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// The three song makers side by side: what each does and what you can
/// change in it. Opened from "Compare" under the engine picker.
Future<void> showEngineComparison(BuildContext context, HumEngine current) {
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: PracticePalette.paper,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (context) => SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(Space.lg, 0, Space.lg, Space.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Three ways to make your song',
              style: TextStyle(
                color: PracticePalette.brown,
                fontSize: 18,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: Space.xs),
            const Text(
              'Each makes its own song from the same hum. Switching keeps your hum; Band also keeps its edits.',
              style: TextStyle(color: PracticePalette.mutedBrown, fontSize: 13),
            ),
            const SizedBox(height: Space.md),
            for (final engine in HumEngine.values)
              _EngineCard(engine: engine, current: engine == current),
          ],
        ),
      ),
    ),
  );
}

class _EngineCard extends StatelessWidget {
  const _EngineCard({required this.engine, required this.current});

  final HumEngine engine;
  final bool current;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: Space.sm),
      padding: const EdgeInsets.all(Space.md),
      decoration: BoxDecoration(
        color: current
            ? PracticePalette.lightGold.withValues(alpha: 0.22)
            : PracticePalette.ivory,
        borderRadius: Radii.cardRadius,
        border: Border.all(
          color: current ? PracticePalette.gold : PracticePalette.lightGold,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                engine.label,
                style: const TextStyle(
                  color: PracticePalette.brown,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const Spacer(),
              if (current)
                const Text(
                  'Selected',
                  style: TextStyle(color: PracticePalette.gold, fontSize: 12),
                ),
            ],
          ),
          const SizedBox(height: Space.xs),
          Text(
            engine.summary,
            style: const TextStyle(color: PracticePalette.brown, fontSize: 14),
          ),
          const SizedBox(height: Space.xs),
          _Line(Icons.layers_outlined, engine.howItWorks),
          _Line(Icons.tune_rounded, engine.youCanChange),
          _Line(
            engine.editableByChat
                ? Icons.chat_bubble_outline_rounded
                : Icons.speaker_notes_off_outlined,
            engine.editableByChat
                ? 'Chat edits: yes.'
                : 'Chat edits: no. Chatting switches to Band.',
          ),
        ],
      ),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line(this.icon, this.text);

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: Space.xs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 16, color: PracticePalette.gold),
          const SizedBox(width: Space.xs),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(
                color: PracticePalette.mutedBrown,
                fontSize: 13,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
