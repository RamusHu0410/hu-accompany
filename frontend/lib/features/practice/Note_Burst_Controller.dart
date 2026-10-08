import 'dart:math';
import 'package:flutter/foundation.dart';

/// One music-note glyph in flight: spawned at the disk's rim, drifting
/// outward, spinning on its own axis, and fading/greying out over its
/// lifespan.
class NoteParticle {
  double angle; // position around the disk, radians — fixed at spawn
  double radius; // current distance from the disk's center, px
  final double outwardSpeed; // px/s
  double spin; // current self-rotation, radians
  final double spinSpeed; // radians/s, signed
  double age; // seconds since spawn
  final double lifespan; // seconds until fully faded
  final String glyph;
  final double baseSize;

  NoteParticle({
    required this.angle,
    required this.radius,
    required this.outwardSpeed,
    required this.spin,
    required this.spinSpeed,
    required this.lifespan,
    required this.glyph,
    required this.baseSize,
  }) : age = 0;

  /// 0 at spawn, 1 once fully faded — drives both opacity and color drift
  /// in the painter.
  double get t => (age / lifespan).clamp(0.0, 1.0);
}

/// Owns the note-burst particle list and its physics. Knows nothing about
/// rendering — call [tick] once per frame with the disk's current angular
/// velocity and the widget layer (NoteBurstLayer) reads [particles] to
/// paint.
class NoteBurstController extends ChangeNotifier {
  final List<NoteParticle> particles = [];

  static const _glyphs = ['♪', '♫', '♬', '♩'];
  final Random _rng = Random();
  double _spawnAccumulator = 0;

  /// Advances all particles by [dt] seconds and spawns new ones if the
  /// disk is currently spinning fast enough. [angularVelocity] is in
  /// rad/s (sign ignored — only speed matters); [diskRadius] is the
  /// on-screen disk radius in px, so notes spawn right at its rim.
  void tick(
    double dt, {
    required double angularVelocity,
    required double diskRadius,
  }) {
    final speed = angularVelocity.abs();

    // Spawn rate scales with spin speed — a slow drag barely spits out
    // any notes, a hard flick showers them.
    if (speed > 0.5) {
      _spawnAccumulator += dt * (speed / (2 * pi)) * 4.5;
      while (_spawnAccumulator >= 1) {
        _spawnAccumulator -= 1;
        _spawnNote(diskRadius, speed);
      }
    }

    for (final p in particles) {
      p.age += dt;
      p.radius += p.outwardSpeed * dt;
      p.spin += p.spinSpeed * dt;
    }
    particles.removeWhere((p) => p.age >= p.lifespan);

    notifyListeners();
  }

  void _spawnNote(double diskRadius, double speed) {
    particles.add(
      NoteParticle(
        angle: _rng.nextDouble() * 2 * pi,
        radius: diskRadius * (0.85 + _rng.nextDouble() * 0.15),
        outwardSpeed: 40 + _rng.nextDouble() * 40 + speed * 4,
        spin: _rng.nextDouble() * 2 * pi,
        spinSpeed: (_rng.nextBool() ? 1 : -1) * (1.5 + _rng.nextDouble() * 2),
        lifespan: 0.9 + _rng.nextDouble() * 0.5,
        glyph: _glyphs[_rng.nextInt(_glyphs.length)],
        baseSize: (14 + _rng.nextDouble() * 10) * 1.5,
      ),
    );
  }
}