import 'package:flutter/material.dart';

import 'package:hu_accomponist/integrations/hum/song_style.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// The band engine's genre and mood. Only reports taps; the controller makes
/// the song again.
class SongStylePicker extends StatelessWidget {
  const SongStylePicker({
    super.key,
    required this.genre,
    required this.mood,
    required this.enabled,
    required this.onGenre,
    required this.onMood,
  });

  final SongGenre? genre;
  final SongMood? mood;

  /// False while a song is being made, so taps don't pile up.
  final bool enabled;
  final ValueChanged<SongGenre> onGenre;
  final ValueChanged<SongMood> onMood;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(Space.md),
      decoration: BoxDecoration(
        color: PracticePalette.paper,
        borderRadius: Radii.cardRadius,
        border: Border.all(
          color: PracticePalette.lightGold.withValues(alpha: 0.65),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _Heading('GENRE'),
          const SizedBox(height: Space.xs),
          _Chips(
            options: [
              for (final option in SongGenre.values)
                (option.label, option == genre, () => onGenre(option)),
            ],
            enabled: enabled,
            keyPrefix: 'genre',
          ),
          const SizedBox(height: Space.md),
          const _Heading('MOOD'),
          const SizedBox(height: Space.xs),
          _Chips(
            options: [
              for (final option in SongMood.values)
                (option.label, option == mood, () => onMood(option)),
            ],
            enabled: enabled,
            keyPrefix: 'mood',
          ),
        ],
      ),
    );
  }
}

class _Chips extends StatelessWidget {
  const _Chips({
    required this.options,
    required this.enabled,
    required this.keyPrefix,
  });

  final List<(String, bool, VoidCallback)> options;
  final bool enabled;
  final String keyPrefix;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: Space.xs,
      runSpacing: Space.xs,
      children: [
        for (final (label, selected, onTap) in options)
          ChoiceChip(
            key: ValueKey('$keyPrefix-$label'),
            label: Text(label),
            selected: selected,
            onSelected: enabled ? (_) => onTap() : null,
            showCheckmark: false,
            selectedColor: PracticePalette.gold,
            backgroundColor: PracticePalette.paper,
            side: const BorderSide(color: PracticePalette.lightGold),
            labelStyle: TextStyle(
              color: selected ? PracticePalette.paper : PracticePalette.brown,
              fontSize: 13,
              fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
            ),
          ),
      ],
    );
  }
}

class _Heading extends StatelessWidget {
  const _Heading(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Text(
    text,
    style: const TextStyle(
      color: PracticePalette.gold,
      fontSize: 11,
      letterSpacing: 2.4,
      fontWeight: FontWeight.w700,
    ),
  );
}
