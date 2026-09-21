import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:hu_accomponist/features/home/Vinyl_Disk_Painter.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// Splash shown while the app boots — a small version of the same vinyl
/// disk used throughout the app, coming up to speed the way a platter
/// actually does. Swaps to [child] once [minDuration] has elapsed.
class Vinyl_Loading_Screen extends StatefulWidget {
  final Widget child;
  final Duration minDuration;
  const Vinyl_Loading_Screen({
    super.key,
    required this.child,
    this.minDuration = const Duration(milliseconds: 900),
  });

  @override
  State<Vinyl_Loading_Screen> createState() => _Vinyl_Loading_ScreenState();
}

class _Vinyl_Loading_ScreenState extends State<Vinyl_Loading_Screen>
    with SingleTickerProviderStateMixin {
  /// Used purely as a clock: it runs far longer than any boot, and the
  /// rotation is derived from elapsed seconds rather than from a repeating
  /// 0→1 ramp. A repeating controller can't express spin-up, because every
  /// cycle would restart the easing and the disk would visibly stutter once
  /// per revolution.
  late final AnimationController _clock;
  bool _done = false;

  static const int _clockSeconds = 60;

  /// Target speed once the platter is up to it, in turns per second.
  static const double _turnsPerSecond = 0.5;

  /// Spin-up time constant. The platter reaches ~95% of target speed after
  /// about 3x this, i.e. roughly 0.8s — in step with [minDuration] so the
  /// disk looks settled, not still accelerating, at the moment it hands off.
  static const double _rampSeconds = 0.28;

  @override
  void initState() {
    super.initState();
    _clock = AnimationController(
      vsync: this,
      duration: const Duration(seconds: _clockSeconds),
    )..forward();
    Future.delayed(widget.minDuration, () {
      if (mounted) setState(() => _done = true);
    });
  }

  @override
  void dispose() {
    _clock.dispose();
    super.dispose();
  }

  /// Exact integral of an exponential approach to target speed —
  /// v(t) = target * (1 - e^(-t/tau)) — so angle, speed and acceleration
  /// are all continuous. That continuity is what reads as "premium"
  /// rather than a disk that simply snaps into a constant spin.
  double _angleAt(double seconds) {
    final eased =
        seconds + _rampSeconds * (math.exp(-seconds / _rampSeconds) - 1);
    return eased * _turnsPerSecond * 2 * math.pi;
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: Motion.page,
      switchInCurve: Motion.enter,
      switchOutCurve: Motion.exit,
      // The splash lifts and fades as the app fades up underneath, instead
      // of the two simply cross-dissolving at the same depth.
      transitionBuilder: (child, animation) {
        final isSplash = child.key == const ValueKey('vinyl-loading');
        return FadeTransition(
          opacity: animation,
          child: ScaleTransition(
            scale: isSplash
                ? Tween<double>(begin: 1.08, end: 1.0).animate(animation)
                : Tween<double>(begin: 0.98, end: 1.0).animate(animation),
            child: child,
          ),
        );
      },
      child: _done ? widget.child : _splash(),
    );
  }

  Widget _splash() {
    return Container(
      key: const ValueKey('vinyl-loading'),
      color: TurntablePalette.background,
      child: Center(
        child: AnimatedBuilder(
          animation: _clock,
          builder: (context, _) => VinylDisk(
            size: 64,
            rotation: _angleAt(_clock.value * _clockSeconds),
            label: '',
            diskColor: TurntablePalette.diskPractice,
          ),
        ),
      ),
    );
  }
}
