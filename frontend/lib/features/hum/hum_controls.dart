import 'package:flutter/material.dart';

import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// "Your song": which engine makes it, and the three faders that shape it.
/// Moving a fader only reports the value; the song is remade when it is let go.
class HumControls extends StatelessWidget {
  const HumControls({
    super.key,
    required this.engine,
    required this.settings,
    required this.onEngine,
    required this.onFader,
    required this.onFaderEnd,
    required this.onReset,
  });

  final HumEngine engine;
  final SongSettings settings;
  final ValueChanged<HumEngine> onEngine;
  final void Function({double? emotion, double? speed, double? pitch}) onFader;
  final VoidCallback onFaderEnd;
  final VoidCallback onReset;

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
          Row(
            children: [
              const Expanded(child: _Heading('YOUR SONG')),
              TextButton(
                onPressed: onReset,
                style: TextButton.styleFrom(
                  foregroundColor: PracticePalette.gold,
                ),
                child: const Text('Reset'),
              ),
            ],
          ),
          SegmentedButton<HumEngine>(
            showSelectedIcon: false,
            segments: [
              for (final option in HumEngine.values)
                ButtonSegment(value: option, label: Text(option.label)),
            ],
            selected: {engine},
            onSelectionChanged: (picked) => onEngine(picked.first),
            style: SegmentedButton.styleFrom(
              foregroundColor: PracticePalette.mutedBrown,
              selectedForegroundColor: PracticePalette.paper,
              selectedBackgroundColor: PracticePalette.gold,
              side: const BorderSide(color: PracticePalette.lightGold),
            ),
          ),
          const SizedBox(height: Space.sm),
          _Fader(
            label: 'Mood',
            low: 'Moody',
            high: 'Bright',
            value: settings.emotion,
            onChanged: (v) => onFader(emotion: v),
            onChangeEnd: onFaderEnd,
          ),
          _Fader(
            label: 'Speed',
            low: 'Slower',
            high: 'Faster',
            value: settings.speed,
            onChanged: (v) => onFader(speed: v),
            onChangeEnd: onFaderEnd,
          ),
          _Fader(
            label: 'Pitch',
            low: 'Lower',
            high: 'Higher',
            value: settings.pitch,
            onChanged: (v) => onFader(pitch: v),
            onChangeEnd: onFaderEnd,
          ),
        ],
      ),
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

class _Fader extends StatelessWidget {
  const _Fader({
    required this.label,
    required this.low,
    required this.high,
    required this.value,
    required this.onChanged,
    required this.onChangeEnd,
  });

  final String label;
  final String low;
  final String high;
  final double value;
  final ValueChanged<double> onChanged;
  final VoidCallback onChangeEnd;

  @override
  Widget build(BuildContext context) {
    const small = TextStyle(color: PracticePalette.mutedBrown, fontSize: 11);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            color: PracticePalette.brown,
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
        ),
        SliderTheme(
          data: SliderTheme.of(context).copyWith(
            activeTrackColor: PracticePalette.gold,
            inactiveTrackColor: PracticePalette.lightGold.withValues(
              alpha: 0.5,
            ),
            thumbColor: PracticePalette.gold,
            overlayColor: PracticePalette.gold.withValues(alpha: 0.15),
          ),
          child: Slider(
            value: value,
            onChanged: onChanged,
            onChangeEnd: (_) => onChangeEnd(),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: Space.md),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(low, style: small),
              Text(high, style: small),
            ],
          ),
        ),
        const SizedBox(height: Space.xs),
      ],
    );
  }
}
