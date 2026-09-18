import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:liquid_glass_easy/liquid_glass_easy.dart';
import 'package:hu_accomponist/src/rust/frb_generated.dart';
import 'package:hu_accomponist/src/rust/models.dart';
import 'package:hu_accomponist/src/rust/api.dart';

class Draggable_Recorder_Button extends StatefulWidget {
  final void Function(bool isRecording) onToggle;

  /// Tints the pulse halo — lets the score screen reflect the last phrase's
  /// verdict without any extra chrome on top of the button.
  final Color accent;

  /// Fired once per phrase, the moment Rust finishes analyzing it.
  /// [phraseNumber] is 1-indexed within this recording. The backend owns
  /// session grouping (see Phrase_Send2_Server.dart) — this widget no
  /// longer invents a client-side session id.
  final void Function(int phraseNumber, List<Notes> notes)? onPhrase;

  const Draggable_Recorder_Button({
    super.key,
    required this.onToggle,
    this.onPhrase,
    this.accent = const Color(0xFF9A7A2C),
  });

  @override
  State<Draggable_Recorder_Button> createState() =>
      _Draggable_Recorder_ButtonState();
}

class _Draggable_Recorder_ButtonState extends State<Draggable_Recorder_Button>
    with SingleTickerProviderStateMixin {
  bool _isRecording = false;
  Duration _elapsed = Duration.zero;
  Timer? _timer;
  Offset _position = const Offset(20, 400);

  // Owns the live notesStream() subscription for the current recording.
  // Null whenever we're not recording.
  StreamSubscription<List<Notes>>? _phraseSubscription;
  int _phraseNumber = 0;

  // Approximate footprint of the whole draggable widget (label row +
  // spacing + the 100x100 icon stack) — used to keep it fully on-screen
  // when dragged, since Positioned won't clamp this for us.
  static const double _buttonWidth = 100.0;
  static const double _buttonHeight = 156.0;

  // Drives both the idle "tap to record" breathing halo and the faster
  // recording pulse — same controller, different period.
  late final AnimationController _pulseCtrl;

  static const Duration _idlePeriod = Duration(milliseconds: 2400);
  static const Duration _recordingPeriod = Duration(milliseconds: 1100);

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(vsync: this, duration: _idlePeriod)
      ..repeat();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _phraseSubscription?.cancel();
    _pulseCtrl.dispose();
    super.dispose();
  }

  Future<void> _startRecording() async {
    _phraseNumber = 0;

    try {
      await RustLib.init(); // flutter_rust_bridge no-ops if already initialized

      // ASSUMPTION: api.dart exposes a startRecording()/stopRecording()
      // pair alongside notesStream() — mirroring what the old
      // start_recording/stop_recording native symbols did, but through
      // the Rust bridge instead of raw FFI. Uncomment once the real
      // function names in api.dart are confirmed; without this,
      // notesStream() is subscribed but Rust is never actually told to
      // start capturing audio.
      // await startRecording();

      _phraseSubscription = notesStream().listen(
        (List<Notes> phrase) {
          _phraseNumber += 1;
          widget.onPhrase?.call(_phraseNumber, phrase);
        },
        onError: (Object error, StackTrace stackTrace) {
          debugPrint(
            '[Draggable_Recorder_Button] notesStream error: $error',
          );
        },
      );
    } catch (error, stackTrace) {
      debugPrint(
        '[Draggable_Recorder_Button] Failed to start recording: $error',
      );
      debugPrintStack(stackTrace: stackTrace);
    }
  }

  Future<void> _stopRecording() async {
    await _phraseSubscription?.cancel();
    _phraseSubscription = null;

    // ASSUMPTION: pairs with the commented-out startRecording() call
    // above — see that comment for context.
    // await stopRecording();
  }

  void _toggle() {
    if (_isRecording) {
      _timer?.cancel();
      setState(() => _isRecording = false);
      _pulseCtrl.duration = _idlePeriod;
      _pulseCtrl.repeat();
      _stopRecording();
    } else {
      setState(() {
        _isRecording = true;
        _elapsed = Duration.zero;
      });
      _pulseCtrl.duration = _recordingPeriod;
      _pulseCtrl.repeat();
      _timer = Timer.periodic(const Duration(seconds: 1), (_) {
        setState(() => _elapsed += const Duration(seconds: 1));
      });
      _startRecording();
    }
    widget.onToggle(_isRecording);
  }

  String get _elapsedLabel {
    final m = _elapsed.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = _elapsed.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    return Positioned(
      left: _position.dx,
      top: _position.dy,
      child: GestureDetector(
        onPanUpdate: (details) {
          final screenSize = MediaQuery.of(context).size;
          final maxX = screenSize.width - _buttonWidth;
          final maxY = screenSize.height - _buttonHeight;
          setState(() {
            final next = _position + details.delta;
            _position = Offset(
              next.dx.clamp(0.0, maxX < 0 ? 0.0 : maxX),
              next.dy.clamp(0.0, maxY < 0 ? 0.0 : maxY),
            );
          });
        },
        onTap: _toggle,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 250),
              child: Text(
                _isRecording ? _elapsedLabel : 'Tap to record',
                key: ValueKey(_isRecording),
                style: TextStyle(
                  color: _isRecording
                      ? const Color(0xFF4D4A45)
                      : const Color(0xFF77736B),
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.2,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: 100,
              height: 100,
              child: Stack(
                alignment: Alignment.center,
                children: [
                  // Breathing halo — the idle hint that this circle is
                  // tappable, and the live indicator once recording.
                  Positioned.fill(
                    child: IgnorePointer(
                      child: AnimatedBuilder(
                        animation: _pulseCtrl,
                        builder: (_, _) => CustomPaint(
                          painter: _PulseHaloPainter(
                            progress: _pulseCtrl.value,
                            color: _isRecording
                                ? widget.accent
                                : const Color(0xFF9A8F7E),
                            strength: _isRecording ? 0.38 : 0.24,
                          ),
                        ),
                      ),
                    ),
                  ),
                  AnimatedContainer(
                      duration: const Duration(milliseconds: 300),
                      curve: Curves.easeInOut,
                      width: 64,
                      height: 64,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.22),
                            blurRadius: 16,
                            offset: const Offset(0, 6),
                          ),
                          BoxShadow(
                            color: Colors.white.withValues(alpha: 0.55),
                            blurRadius: 10,
                            spreadRadius: 1,
                          ),
                        ],
                      ),
                      child: LiquidGlassLens(
                        style: LiquidGlassStyle(
                          shape:
                              const LiquidGlassShape.continuousRoundedRectangle(
                                cornerRadius: 32,
                              ),
                          appearance: LiquidGlassAppearance(
                            // A neutral transparent lens: no purple idle
                            // tint or red recording tint.
                            color: Colors.white.withValues(alpha: 0.10),
                          ),
                          refraction: const LiquidGlassRefraction(
                            distortion: 0.12,
                            distortionWidth: 20,
                            magnification: 1.05,
                          ),
                        ),
                        child: Center(
                          child: AnimatedSwitcher(
                            duration: const Duration(milliseconds: 200),
                            child: Icon(
                              _isRecording
                                  ? Icons.stop_rounded
                                  : Icons.mic_rounded,
                              key: ValueKey(_isRecording),
                              color: const Color(0xFF5F5A52),
                              size: 30,
                            ),
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 10),
            SizedBox(
              height: 14,
              child: AnimatedBuilder(
                animation: _pulseCtrl,
                builder: (_, _) => CustomPaint(
                  size: const Size(56, 14),
                  painter: _WaveHintPainter(
                    progress: _pulseCtrl.value,
                    active: _isRecording,
                    color: _isRecording
                        ? widget.accent
                        : const Color(0xFF9A8F7E),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Two soft rings expanding out of the button — barely-there when idle,
/// firmer while recording.
class _PulseHaloPainter extends CustomPainter {
  final double progress;
  final Color color;
  final double strength;

  _PulseHaloPainter({
    required this.progress,
    required this.color,
    required this.strength,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    for (int i = 0; i < 2; i++) {
      final t = (progress + i * 0.5) % 1.0;
      final radius = 32 + t * 18;
      final opacity = strength * (1 - t);
      if (opacity <= 0.01) continue;
      canvas.drawCircle(
        center,
        radius,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.4
          ..color = color.withValues(alpha: opacity),
      );
    }
  }

  @override
  bool shouldRepaint(_PulseHaloPainter old) =>
      old.progress != progress || old.color != color || old.strength != strength;
}

/// Five bars that stay flat-ish as a hint when idle and sway while
/// recording, so the button reads as "listening" without extra chrome.
class _WaveHintPainter extends CustomPainter {
  final double progress;
  final bool active;
  final Color color;

  _WaveHintPainter({
    required this.progress,
    required this.active,
    required this.color,
  });

  @override
  void paint(Canvas canvas, Size size) {
    const barCount = 5;
    final gap = size.width / barCount;
    final midY = size.height / 2;
    final paint = Paint()
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 2.5
      ..color = color.withValues(alpha: active ? 0.75 : 0.35);

    for (int i = 0; i < barCount; i++) {
      final phase = (progress + i / barCount) * 2 * pi;
      final amplitude = active ? 5.0 : 1.6;
      final half = 1.5 + amplitude * (0.5 + 0.5 * sin(phase));
      final x = gap * (i + 0.5);
      canvas.drawLine(Offset(x, midY - half), Offset(x, midY + half), paint);
    }
  }

  @override
  bool shouldRepaint(_WaveHintPainter old) =>
      old.progress != progress || old.active != active || old.color != color;
}