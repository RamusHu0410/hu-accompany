import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// How firm the haptic tick on a tap should be. [none] is for controls
/// that fire continuously (dragging, scrubbing) where a tick per event
/// would turn into a buzz.
enum PressHaptic { none, selection, light, medium }

/// Wraps a tappable surface so it dips slightly under the finger and ticks
/// once on contact.
///
/// This owns the tap rather than sitting outside an existing [InkWell]:
/// two tap recognizers competing in the gesture arena means the outer one
/// is handed `onTapCancel` the moment the inner one wins, which shows up
/// as the press animation flickering back out mid-press. Keeping the ripple
/// and the scale in the same widget avoids that entirely.
class PressScale extends StatefulWidget {
  final Widget child;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;

  /// How far down the surface dips. Large targets need less travel than
  /// small ones to read as the same amount of "give".
  final double pressedScale;

  final PressHaptic haptic;
  final BorderRadius borderRadius;

  /// Ripple tint. Null leaves the theme default; [Colors.transparent]
  /// turns the ripple off for surfaces where it would muddy a gradient.
  final Color? splashColor;
  final Color? highlightColor;

  const PressScale({
    super.key,
    required this.child,
    this.onTap,
    this.onLongPress,
    this.pressedScale = 0.97,
    this.haptic = PressHaptic.selection,
    this.borderRadius = Radii.cardRadius,
    this.splashColor,
    this.highlightColor,
  });

  @override
  State<PressScale> createState() => _PressScaleState();
}

class _PressScaleState extends State<PressScale> {
  bool _pressed = false;

  void _setPressed(bool value) {
    if (_pressed == value) return;
    setState(() => _pressed = value);
  }

  void _handleTap() {
    switch (widget.haptic) {
      case PressHaptic.none:
        break;
      case PressHaptic.selection:
        HapticFeedback.selectionClick();
      case PressHaptic.light:
        HapticFeedback.lightImpact();
      case PressHaptic.medium:
        HapticFeedback.mediumImpact();
    }
    widget.onTap?.call();
  }

  @override
  Widget build(BuildContext context) {
    final enabled = widget.onTap != null || widget.onLongPress != null;

    return AnimatedScale(
      scale: _pressed && enabled ? widget.pressedScale : 1.0,
      duration: Motion.press,
      curve: Motion.standard,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: enabled ? _handleTap : null,
          onLongPress: widget.onLongPress,
          onTapDown: enabled ? (_) => _setPressed(true) : null,
          onTapUp: enabled ? (_) => _setPressed(false) : null,
          onTapCancel: enabled ? () => _setPressed(false) : null,
          borderRadius: widget.borderRadius,
          splashColor: widget.splashColor,
          highlightColor: widget.highlightColor,
          child: widget.child,
        ),
      ),
    );
  }
}
