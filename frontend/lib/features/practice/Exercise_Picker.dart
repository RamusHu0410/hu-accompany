import 'package:flutter/material.dart';

import 'package:hu_accomponist/features/practice/Exercise.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';
import 'package:hu_accomponist/shared/ui/Press_Scale.dart';

/// What the player chose in [ExercisePicker].
class ExerciseChoice {
  final Exercise exercise;
  final int bpm;
  final int octave;
  const ExerciseChoice(this.exercise, this.bpm, this.octave);
}

/// Bottom sheet for choosing an exercise, tempo and octave.
class ExercisePicker extends StatefulWidget {
  const ExercisePicker({super.key});

  static Future<ExerciseChoice?> show(BuildContext context) {
    return showModalBottomSheet<ExerciseChoice>(
      context: context,
      backgroundColor: PracticePalette.paper,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(Radii.modal)),
      ),
      builder: (_) => const ExercisePicker(),
    );
  }

  @override
  State<ExercisePicker> createState() => _ExercisePickerState();
}

class _ExercisePickerState extends State<ExercisePicker> {
  Exercise _exercise = Exercise.all.first;
  int _bpm = Exercise.defaultTempo;
  int _octave = Exercise.defaultOctave;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          Space.lg,
          Space.md,
          Space.lg,
          Space.lg,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'EXERCISE',
              style: TextStyle(
                color: PracticePalette.gold,
                fontSize: 11,
                letterSpacing: 2.4,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: Space.sm),
            for (final e in Exercise.all) _exerciseRow(e),
            const SizedBox(height: Space.md),
            _label('Tempo'),
            _chips<int>(
              Exercise.tempos,
              _bpm,
              (v) => '$v bpm',
              (v) => setState(() => _bpm = v),
            ),
            const SizedBox(height: Space.md),
            _label('Starting octave'),
            _chips<int>(
              Exercise.octaves,
              _octave,
              (v) => 'C$v',
              (v) => setState(() => _octave = v),
            ),
            const SizedBox(height: Space.xs),
            Text(
              'Higher octaves are detected more accurately.',
              style: TextStyle(
                color: PracticePalette.mutedBrown.withValues(alpha: 0.8),
                fontSize: 12,
              ),
            ),
            const SizedBox(height: Space.lg),
            PressScale(
              onTap: () => Navigator.pop(
                context,
                ExerciseChoice(_exercise, _bpm, _octave),
              ),
              borderRadius: Radii.pillRadius,
              child: Container(
                height: 48,
                alignment: Alignment.center,
                decoration: const BoxDecoration(
                  color: PracticePalette.gold,
                  borderRadius: Radii.pillRadius,
                ),
                child: const Text(
                  'Use this exercise',
                  style: TextStyle(
                    color: PracticePalette.paper,
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _label(String text) => Padding(
    padding: const EdgeInsets.only(bottom: Space.xs),
    child: Text(
      text,
      style: const TextStyle(
        color: PracticePalette.brown,
        fontSize: 13,
        fontWeight: FontWeight.w600,
      ),
    ),
  );

  Widget _exerciseRow(Exercise e) {
    final selected = e.id == _exercise.id;
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.xs),
      child: PressScale(
        onTap: () => setState(() => _exercise = e),
        borderRadius: Radii.cardRadius,
        child: AnimatedContainer(
          duration: Motion.fast,
          padding: const EdgeInsets.all(Space.sm),
          decoration: BoxDecoration(
            color: selected
                ? PracticePalette.gold.withValues(alpha: 0.10)
                : PracticePalette.ivory,
            borderRadius: Radii.cardRadius,
            border: Border.all(
              color: selected ? PracticePalette.gold : PracticePalette.lightGold,
            ),
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      e.title,
                      style: const TextStyle(
                        color: PracticePalette.brown,
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: Space.xxs),
                    Text(
                      e.description,
                      style: const TextStyle(
                        color: PracticePalette.mutedBrown,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              if (selected)
                const Icon(
                  Icons.check_rounded,
                  size: 18,
                  color: PracticePalette.gold,
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _chips<T>(
    List<T> values,
    T selected,
    String Function(T) label,
    ValueChanged<T> onPick,
  ) {
    return Wrap(
      spacing: Space.xs,
      children: [
        for (final v in values)
          ChoiceChip(
            label: Text(label(v)),
            selected: v == selected,
            onSelected: (_) => onPick(v),
            selectedColor: PracticePalette.gold.withValues(alpha: 0.18),
            backgroundColor: PracticePalette.ivory,
            side: BorderSide(
              color: v == selected
                  ? PracticePalette.gold
                  : PracticePalette.lightGold,
            ),
            labelStyle: TextStyle(
              color: v == selected
                  ? PracticePalette.brown
                  : PracticePalette.mutedBrown,
              fontWeight: FontWeight.w600,
            ),
            showCheckmark: false,
          ),
      ],
    );
  }
}
