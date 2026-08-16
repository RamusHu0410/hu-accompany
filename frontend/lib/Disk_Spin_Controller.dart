import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';
import 'Vinyl_Disk_Painter.dart';

/// Wraps a [VinylDisk] with real touch-and-spin physics: drag it in a
/// circle and it picks up angular momentum; let go and it keeps spinning
/// while friction slows it down, exactly like flicking a real record on a
/// platter. Spin it hard enough — enough total rotation travelled during
/// that free-spin decay — and [onActivated] fires once, so the caller can
/// zoom/blur into whatever page this disk represents.
class SpinnableDisk extends StatefulWidget {
  final double size;
  final String label;
  final String? sublabel;
  final Color labelColor;
  final Color diskColor;
  final VoidCallback onActivated;

  /// Total radians the disk must travel during its free-spin decay before
  /// activation fires. 4π ≈ two full turns — enough that a lazy nudge won't
  /// accidentally trigger navigation, but a real flick will.
  final double activationRadians;

  const SpinnableDisk({
    super.key,
    required this.size,
    required this.label,
    required this.onActivated,
    this.sublabel,
    this.labelColor = const Color(0xFFEDE6DA),
    this.diskColor = const Color(0xFF0B0B0D),
    this.activationRadians = 4 * pi,
  });

  @override
  State<SpinnableDisk> createState() => SpinnableDiskState();
}

class SpinnableDiskState extends State<SpinnableDisk>
    with SingleTickerProviderStateMixin {
  late final AnimationController _spinController;

  double _rotation = 0;
  double _lastDragAngle = 0;
  double _angularVelocity = 0; // rad/s, signed, smoothed
  DateTime? _lastDragTime;
  bool _dragging = false;
  bool _activatedThisSpin = false;
  double _traveledSinceRelease = 0;

  @override
  void initState() {
    super.initState();
    _spinController = AnimationController.unbounded(vsync: this)
      ..addListener(_onSpinTick);
  }

  @override
  void dispose() {
    _spinController.dispose();
    super.dispose();
  }

  double _angleAt(Offset localPosition) {
    final center = Offset(widget.size / 2, widget.size / 2);
    final d = localPosition - center;
    return atan2(d.dy, d.dx);
  }

  // Shortest signed angular difference, so crossing the -π/π seam doesn't
  // register as a huge jump backwards.
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

  void _onPanStart(DragStartDetails details) {
    _spinController.stop();
    _dragging = true;
    _activatedThisSpin = false;
    _traveledSinceRelease = 0;
    _angularVelocity = 0;
    _lastDragAngle = _angleAt(details.localPosition);
    _lastDragTime = DateTime.now();
  }

  void _onPanUpdate(DragUpdateDetails details) {
    final now = DateTime.now();
    final angle = _angleAt(details.localPosition);
    final delta = _shortestDelta(_lastDragAngle, angle);

    final dtMs = _lastDragTime == null
        ? 16
        : now.difference(_lastDragTime!).inMilliseconds.clamp(1, 200);
    final dt = dtMs / 1000.0;

    setState(() => _rotation += delta);

    // Smoothed instantaneous angular velocity, so a single jittery pointer
    // frame doesn't dominate the fling computed on release.
    final instant = delta / dt;
    _angularVelocity = _angularVelocity * 0.7 + instant * 0.3;

    _lastDragAngle = angle;
    _lastDragTime = now;
  }

  void _onPanEnd(DragEndDetails details) {
    _dragging = false;
    // Only a real flick sends it spinning — a slow drag just leaves the
    // disk where it was, like nudging a real record by hand.
    const minSpinVelocity = 3.0; // rad/s
    if (_angularVelocity.abs() < minSpinVelocity) {
      return;
    }
    final simulation = FrictionSimulation(0.86, _rotation, _angularVelocity);
    _spinController.animateWith(simulation);
  }

  void _onSpinTick() {
    final newRotation = _spinController.value;
    final delta = newRotation - _rotation;
    _traveledSinceRelease += delta.abs();
    setState(() => _rotation = newRotation);

    if (!_activatedThisSpin && _traveledSinceRelease >= widget.activationRadians) {
      _activatedThisSpin = true;
      widget.onActivated();
    }

    // FrictionSimulation asymptotically approaches zero velocity but never
    // truly hits it — stop the ticker once it's crawling so this isn't
    // animating forever in the background.
    if (_spinController.velocity.abs() < 0.02 && !_dragging) {
      _spinController.stop();
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onPanStart: _onPanStart,
      onPanUpdate: _onPanUpdate,
      onPanEnd: _onPanEnd,
      child: VinylDisk(
        size: widget.size,
        rotation: _rotation,
        label: widget.label,
        sublabel: widget.sublabel,
        labelColor: widget.labelColor,
        diskColor: widget.diskColor,
      ),
    );
  }
}