import 'package:flutter/material.dart';

import 'package:hu_accomponist/features/hum/raw_piano_roll.dart';
import 'package:hu_accomponist/features/hum/raw_playback_controller.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// "Your hum, as hummed": the raw notes on a piano roll, played back
/// exactly, on piano or synth, and exported as MIDI. Draws
/// [RawPlaybackController]; every tap goes straight back to it.
class RawHumPanel extends StatelessWidget {
  const RawHumPanel({super.key, required this.playback});

  final RawPlaybackController playback;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: playback,
      builder: (context, _) => Container(
        padding: const EdgeInsets.all(Space.md),
        decoration: BoxDecoration(
          color: PracticePalette.paper,
          borderRadius: Radii.cardRadius,
          border: Border.all(
            color: PracticePalette.lightGold.withValues(alpha: 0.65),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'YOUR HUM, AS HUMMED',
              style: TextStyle(
                color: PracticePalette.gold,
                fontSize: 11,
                letterSpacing: 2.4,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: Space.sm),
            _roll(),
            const SizedBox(height: Space.sm),
            _controls(context),
            if (playback.error != null)
              Padding(
                padding: const EdgeInsets.only(top: Space.xs),
                child: Text(
                  playback.error!,
                  style: const TextStyle(
                    color: PracticePalette.alert,
                    fontSize: 13,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _roll() {
    final hum = playback.hum;
    if (hum == null) {
      return SizedBox(
        height: 150,
        child: Center(
          child: playback.loading
              ? const CircularProgressIndicator(
                  strokeWidth: 2.5,
                  color: PracticePalette.gold,
                )
              : const Text(
                  'No notes yet',
                  style: TextStyle(color: PracticePalette.mutedBrown),
                ),
        ),
      );
    }
    return RawPianoRoll(
      hum: hum,
      sounding: playback.sounding,
      position: playback.position,
      isPlaying: playback.isPlaying,
    );
  }

  Widget _controls(BuildContext context) {
    return Wrap(
      spacing: Space.sm,
      runSpacing: Space.xs,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        FilledButton.icon(
          key: const ValueKey('play-my-hum'),
          onPressed: playback.canPlay && !playback.fetchingAudio
              ? playback.togglePlay
              : null,
          icon: playback.fetchingAudio
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: PracticePalette.paper,
                  ),
                )
              : Icon(
                  playback.isPlaying
                      ? Icons.stop_rounded
                      : Icons.play_arrow_rounded,
                ),
          label: Text(playback.isPlaying ? 'Stop' : 'Play my hum'),
          style: FilledButton.styleFrom(
            backgroundColor: PracticePalette.gold,
            foregroundColor: PracticePalette.paper,
          ),
        ),
        SegmentedButton<RawInstrument>(
          showSelectedIcon: false,
          segments: [
            for (final option in RawInstrument.values)
              ButtonSegment(value: option, label: Text(option.label)),
          ],
          selected: {playback.instrument},
          onSelectionChanged: (picked) => playback.setInstrument(picked.first),
          style: SegmentedButton.styleFrom(
            foregroundColor: PracticePalette.mutedBrown,
            selectedForegroundColor: PracticePalette.paper,
            selectedBackgroundColor: PracticePalette.gold,
            side: const BorderSide(color: PracticePalette.lightGold),
          ),
        ),
        Builder(
          builder: (button) => TextButton.icon(
            onPressed: playback.hum == null || playback.exporting
                ? null
                : () => playback.exportMidi(origin: _rectOf(button)),
            icon: const Icon(Icons.ios_share_rounded, size: 18),
            label: const Text('Export MIDI'),
            style: TextButton.styleFrom(foregroundColor: PracticePalette.gold),
          ),
        ),
      ],
    );
  }

  static Rect? _rectOf(BuildContext context) {
    final box = context.findRenderObject() as RenderBox?;
    if (box == null || !box.hasSize) return null;
    return box.localToGlobal(Offset.zero) & box.size;
  }
}
