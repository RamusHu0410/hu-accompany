import 'dart:async';
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../theme/Color_Theme.dart';
import '../theme/Design_Tokens.dart';
import 'Recorder_Painters.dart';
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
  Timer? _timer;

  /// Both tick far more often than the rest of the button changes — the
  /// timer once a second, the drag once a frame — and both used to go
  /// through setState, rebuilding the glass lens and the two painters
  /// along with them. Kept as notifiers so each drives only the one
  /// subtree that reads it.
  final ValueNotifier<Duration> _elapsed = ValueNotifier(Duration.zero);
  final ValueNotifier<Offset> _position = ValueNotifier(
    const Offset(20, 400),
  );

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
    _elapsed.dispose();
    _position.dispose();
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
      // Lighter than the start tick: stopping is a release, and the two
      // being distinguishable by feel means the button can be operated
      // without looking at it.
      HapticFeedback.lightImpact();
      _timer?.cancel();
      setState(() => _isRecording = false);
      _pulseCtrl.duration = _idlePeriod;
      _pulseCtrl.repeat();
      _stopRecording();
    } else {
      HapticFeedback.mediumImpact();
      setState(() => _isRecording = true);
      _elapsed.value = Duration.zero;
      _pulseCtrl.duration = _recordingPeriod;
      _pulseCtrl.repeat();
      _timer = Timer.periodic(const Duration(seconds: 1), (_) {
        _elapsed.value += const Duration(seconds: 1);
      });
      _startRecording();
    }
    widget.onToggle(_isRecording);
  }

  static String _format(Duration elapsed) {
    final m = elapsed.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = elapsed.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    // Built once per real state change and threaded through the position
    // builder as `child`, so dragging only re-runs the Positioned above it.
    final content = GestureDetector(
      onPanUpdate: _onPanUpdate,
      onTap: _toggle,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          AnimatedSwitcher(
            duration: Motion.base,
            switchInCurve: Motion.enter,
            switchOutCurve: Motion.exit,
            child: _isRecording
                ? ValueListenableBuilder<Duration>(
                    key: const ValueKey(true),
                    valueListenable: _elapsed,
                    builder: (context, elapsed, _) =>
                        Text(_format(elapsed), style: _labelStyle(true)),
                  )
                : Text(
                    'Tap to record',
                    key: const ValueKey(false),
                    style: _labelStyle(false),
                  ),
          ),
          const SizedBox(height: Space.sm),
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
                        painter: RecorderPulseHaloPainter(
                          progress: _pulseCtrl.value,
                          color: _isRecording
                              ? widget.accent
                              : RecorderPalette.haloIdle,
                          strength: _isRecording ? 0.38 : 0.24,
                        ),
                      ),
                    ),
                  ),
                ),
                _lens(),
              ],
            ),
          ),
          const SizedBox(height: Space.sm),
          SizedBox(
            height: 14,
            child: AnimatedBuilder(
              animation: _pulseCtrl,
              builder: (_, _) => CustomPaint(
                size: const Size(56, 14),
                painter: RecorderWaveHintPainter(
                  progress: _pulseCtrl.value,
                  active: _isRecording,
                  color: _isRecording
                      ? widget.accent
                      : RecorderPalette.haloIdle,
                ),
              ),
            ),
          ),
        ],
      ),
    );

    return ValueListenableBuilder<Offset>(
      valueListenable: _position,
      child: content,
      builder: (context, pos, child) =>
          Positioned(left: pos.dx, top: pos.dy, child: child!),
    );
  }

  void _onPanUpdate(DragUpdateDetails details) {
    final screenSize = MediaQuery.of(context).size;
    final maxX = screenSize.width - _buttonWidth;
    final maxY = screenSize.height - _buttonHeight;
    final next = _position.value + details.delta;
    _position.value = Offset(
      next.dx.clamp(0.0, maxX < 0 ? 0.0 : maxX),
      next.dy.clamp(0.0, maxY < 0 ? 0.0 : maxY),
    );
  }

  TextStyle _labelStyle(bool recording) => TextStyle(
    color: recording
        ? RecorderPalette.labelActive
        : RecorderPalette.labelIdle,
    fontSize: 14,
    fontWeight: FontWeight.w600,
    letterSpacing: 1.2,
    fontFeatures: const [FontFeature.tabularFigures()],
  );

  Widget _lens() {
    return AnimatedContainer(
      duration: Motion.slow,
      curve: Motion.standard,
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
          shape: const LiquidGlassShape.continuousRoundedRectangle(
            cornerRadius: 32,
          ),
          appearance: LiquidGlassAppearance(
            // A neutral transparent lens: no purple idle tint or red
            // recording tint.
            color: Colors.white.withValues(alpha: 0.10),
          ),
          refraction: const LiquidGlassRefraction(
            distortion: 0.12,
            distortionWidth: 20,
            magnification: 1.05,
          ),
        ),
        child: Center(child: _micIcon()),
      ),
    );
  }

  /// The idle mic breathes in time with the halo so the control reads as
  /// alive and waiting rather than as a static graphic. While recording the
  /// stop square stays still — a moving stop target is harder to hit, and
  /// the halo already carries the liveness at that point.
  Widget _micIcon() {
    final icon = AnimatedSwitcher(
      duration: Motion.fast,
      transitionBuilder: (child, animation) => FadeTransition(
        opacity: animation,
        child: ScaleTransition(scale: animation, child: child),
      ),
      child: Icon(
        _isRecording ? Icons.stop_rounded : Icons.mic_rounded,
        key: ValueKey(_isRecording),
        color: RecorderPalette.icon,
        size: 30,
      ),
    );

    if (_isRecording) return icon;

    return AnimatedBuilder(
      animation: _pulseCtrl,
      child: icon,
      builder: (context, child) {
        // A full sine cycle over the controller's period: out and back,
        // with no discontinuity at the wrap point.
        final breath = sin(_pulseCtrl.value * 2 * pi);
        return Transform.scale(scale: 1 + 0.045 * breath, child: child);
      },
    );
  }
}
