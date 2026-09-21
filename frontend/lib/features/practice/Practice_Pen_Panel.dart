import 'package:flutter/material.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';
import 'package:hu_accomponist/shared/ui/Press_Scale.dart';

/// The annotation pen's settings — colour, nib size, eraser — shown as a
/// floating panel under the palette button.
class PracticePenPanel extends StatelessWidget {
  final List<Color> colors;
  final Color selectedColor;
  final double penSize;
  final bool isErasing;
  final ValueChanged<Color> onColorSelected;
  final ValueChanged<double> onSizeChanged;
  final VoidCallback onEraserToggled;

  const PracticePenPanel({
    super.key,
    required this.colors,
    required this.selectedColor,
    required this.penSize,
    required this.isErasing,
    required this.onColorSelected,
    required this.onSizeChanged,
    required this.onEraserToggled,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 230,
      padding: const EdgeInsets.fromLTRB(
        Space.md,
        Space.md,
        Space.md,
        Space.sm,
      ),
      decoration: BoxDecoration(
        color: PracticePalette.paper,
        borderRadius: Radii.lgRadius,
        border: Border.all(color: PracticePalette.lightGold, width: 1),
        boxShadow: Elevations.overlay(PracticePalette.brown),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'PEN',
            style: TextStyle(
              color: PracticePalette.gold,
              fontSize: 10,
              fontWeight: FontWeight.w700,
              letterSpacing: 2.5,
            ),
          ),
          const SizedBox(height: Space.sm),
          _swatches(),
          const SizedBox(height: Space.sm),
          _rule(),
          const SizedBox(height: Space.sm),
          _sizeRow(context),
          const SizedBox(height: Space.xs),
          _rule(),
          const SizedBox(height: Space.sm),
          _eraserRow(),
        ],
      ),
    );
  }

  Widget _rule() => Container(
    height: 1,
    color: PracticePalette.lightGold.withValues(alpha: 0.5),
  );

  Widget _swatches() {
    return Row(
      children: colors.map((color) {
        final selected = color == selectedColor;
        return Padding(
          padding: const EdgeInsets.only(right: Space.sm),
          child: PressScale(
            onTap: () => onColorSelected(color),
            borderRadius: Radii.pillRadius,
            pressedScale: 0.88,
            child: AnimatedContainer(
              duration: Motion.fast,
              curve: Motion.standard,
              width: 25,
              height: 25,
              decoration: BoxDecoration(
                color: color,
                shape: BoxShape.circle,
                border: Border.all(
                  color: selected
                      ? PracticePalette.gold
                      : Colors.transparent,
                  width: 2,
                ),
              ),
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _sizeRow(BuildContext context) {
    return Row(
      children: [
        const Icon(
          Icons.line_weight_rounded,
          size: 15,
          color: PracticePalette.gold,
        ),
        Expanded(
          child: SliderTheme(
            data: SliderTheme.of(context).copyWith(
              activeTrackColor: PracticePalette.gold,
              inactiveTrackColor: PracticePalette.lightGold.withValues(
                alpha: 0.45,
              ),
              thumbColor: PracticePalette.gold,
              overlayColor: PracticePalette.gold.withValues(alpha: 0.10),
              trackHeight: 1,
              thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 5),
            ),
            child: Slider(
              value: penSize,
              min: 1,
              max: 14,
              onChanged: onSizeChanged,
            ),
          ),
        ),
        SizedBox(
          width: 25,
          child: Text(
            penSize.toStringAsFixed(1),
            textAlign: TextAlign.right,
            style: const TextStyle(
              color: PracticePalette.brown,
              fontSize: 11,
              fontFeatures: [FontFeature.tabularFigures()],
            ),
          ),
        ),
      ],
    );
  }

  Widget _eraserRow() {
    return PressScale(
      onTap: onEraserToggled,
      borderRadius: Radii.cardRadius,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: Space.xxs),
        child: Row(
          children: [
            Icon(
              Icons.auto_fix_normal_outlined,
              size: 16,
              color: isErasing
                  ? PracticePalette.gold
                  : PracticePalette.brown.withValues(alpha: 0.6),
            ),
            const SizedBox(width: Space.sm),
            Text(
              'Eraser',
              style: TextStyle(
                color: isErasing
                    ? PracticePalette.gold
                    : PracticePalette.brown,
                fontSize: 12,
                fontWeight: isErasing ? FontWeight.w700 : FontWeight.w400,
              ),
            ),
            const Spacer(),
            AnimatedContainer(
              duration: Motion.fast,
              curve: Motion.standard,
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: isErasing ? PracticePalette.gold : Colors.transparent,
                border: Border.all(color: PracticePalette.lightGold),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
