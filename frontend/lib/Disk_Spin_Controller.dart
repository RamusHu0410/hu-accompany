import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';
import 'Vinyl_Disk_Painter.dart';

/// Pure physics/state for spinning a disk — no gesture detection of its own.
///
/// Gesture *recognition* (deciding whether a touch is a spin vs. a page
/// swipe) has to happen in exactly one place, or two competing
/// GestureDetectors end up racing in Flutter's gesture arena for the same
/// touch. So this controller doesn't hit-test anything; the owner
/// ([Record_Navigator_Page]) resolves the gesture first, then drives this
/// with plain angle values via [start]/[update]/[end].
///
/// Behaves like a real record: drag it in a circle and it picks up angular
/// momentum; let go and it keeps spinning while friction slows it down.
/// Spin it hard enough — enough total rotation travelled during that
/// free-spin decay — and [onActivated] fires once. If it decays back to
/// rest without ever reaching that, [onSettled] fires instead so the owner
/// can drop back to its "locked" state.
class DiskSpinController extends ChangeNotifier {
  DiskSpinController({
    required TickerProvider vsync,
    required this.onActivated,
    required this.onSettled,
    this.activationRadians = 4 * pi,
  }) : _ticker = AnimationController.unbounded(vsync: vsync) {
    _ticker.addListener(_onTick);
  }

  /// Fires once per spin, when enough free-spin rotation has accumulated.
  final VoidCallback onActivated;

  /// Fires when a spin decays back to rest without ever activating.
  final VoidCallback onSettled;

  /// Total radians the disk must travel during its free-spin decay before
  /// activation fires. 4π ≈ two full turns — enough that a lazy nudge won't
  /// accidentally trigger navigation, but a real flick will.
  final double activationRadians;

  final AnimationController _ticker;

  double rotation = 0;
  double _angularVelocity = 0; // rad/s, signed, smoothed
  double _lastAngle = 0;
  DateTime? _lastTime;
  bool _dragging = false;
  bool _activatedThisSpin = false;
  double _traveledSinceRelease = 0;

  double _shortestDelta(double from, double to) {
    var delta = to - from;
    while (delta > pi) {
      delta -= 2 * pi;
    }
    while (delta < -pi) {
      delta += 2 * pi;
    }
    return delta;
  }

  /// Call once the owner has resolved a touch as a spin (i.e. it already
  /// cleared the rotational deadzone) — `angle` is that same touch's current
  /// angle around the disk center, so there's no jump at handoff.
  void start(double angle) {
    _ticker.stop();
    _dragging = true;
    _activatedThisSpin = false;
    _traveledSinceRelease = 0;
    _angularVelocity = 0;
    _lastAngle = angle;
    _lastTime = DateTime.now();
  }

  void update(double angle) {
    final now = DateTime.now();
    final delta = _shortestDelta(_lastAngle, angle);

    final dtMs = _lastTime == null
        ? 16
        : now.difference(_lastTime!).inMilliseconds.clamp(1, 200);
    final dt = dtMs / 1000.0;

    rotation += delta;

    // Smoothed instantaneous angular velocity, so a single jittery pointer
    // frame doesn't dominate the fling computed on release.
    final instant = delta / dt;
    _angularVelocity = _angularVelocity * 0.7 + instant * 0.3;

    _lastAngle = angle;
    _lastTime = now;
    notifyListeners();
  }

  /// Touch released. Only a real flick sends it spinning — a slow drag just
  /// leaves the disk where it was, like nudging a real record by hand.
  void end() {
    _dragging = false;
    const minSpinVelocity = 3.0; // rad/s
    if (_angularVelocity.abs() < minSpinVelocity) {
      onSettled();
      return;
    }
    final simulation = FrictionSimulation(0.86, rotation, _angularVelocity);
    _ticker.animateWith(simulation);
  }

  /// Grabbing the disk again (mid free-spin) stills it immediately, same as
  /// pressing a hand down on a real spinning record.
  void cancelDecay() {
    if (_ticker.isAnimating) {
      _ticker.stop();
    }
  }

  /// A different disk has just been locked into the platter — reset all
  /// spin state so it starts at rest.
  void resetForNewDisk() {
    _ticker.stop();
    rotation = 0;
    _angularVelocity = 0;
    _dragging = false;
    _activatedThisSpin = false;
    _traveledSinceRelease = 0;
    notifyListeners();
  }

  void _onTick() {
    final newRotation = _ticker.value;
    final delta = newRotation - rotation;
    _traveledSinceRelease += delta.abs();
    rotation = newRotation;
    notifyListeners();

    if (!_activatedThisSpin && _traveledSinceRelease >= activationRadians) {
      _activatedThisSpin = true;
      _ticker.stop();
      onActivated();
      return;
    }

    // FrictionSimulation asymptotically approaches zero velocity but never
    // truly hits it — stop the ticker once it's crawling so this isn't
    // animating forever in the background.
    if (_ticker.velocity.abs() < 0.02 && !_dragging) {
      _ticker.stop();
      if (!_activatedThisSpin) {
        onSettled();
      }
    }
  }

  @override
  void dispose() {
    _ticker.dispose();
    super.dispose();
  }
}

/// Renders a disk driven by a [DiskSpinController]. Purely presentational —
/// carries no gesture detection, so it never competes with a page-level
/// swipe recognizer for the same touch.
class SpinningDisk extends StatelessWidget {
  final DiskSpinController controller;
  final double size;
  final String label;
  final String? sublabel;
  final Color labelColor;
  final Color diskColor;

  const SpinningDisk({
    super.key,
    required this.controller,
    required this.size,
    required this.label,
    this.sublabel,
    this.labelColor = const Color(0xFFEDE6DA),
    this.diskColor = const Color(0xFF0B0B0D),
  });

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) => VinylDisk(
        size: size,
        rotation: controller.rotation,
        label: label,
        sublabel: sublabel,
        labelColor: labelColor,
        diskColor: diskColor,
      ),
    );
  }
}
