import 'dart:async';
import 'package:flutter/material.dart';
import 'package:liquid_glass_easy/liquid_glass_easy.dart';
import 'package:hu_accomponist/src/rust/frb_generated.dart';
import 'package:hu_accomponist/src/rust/models.dart';
import 'package:hu_accomponist/src/rust/api.dart';

class Draggable_Recorder_Button extends StatefulWidget {
  final void Function(bool isRecording) onToggle;

  /// Fired once per phrase, the moment Rust finishes analyzing it.
  /// [phraseNumber] is 1-indexed within this recording. The backend owns
  /// session grouping (see Phrase_Send2_Server.dart) — this widget no
  /// longer invents a client-side session id.
  final void Function(int phraseNumber, List<Notes> notes)? onPhrase;

  const Draggable_Recorder_Button({
    super.key,
    required this.onToggle,
    this.onPhrase,
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
  static const double _buttonHeight = 132.0;

  late final AnimationController _pulseCtrl;
  late final Animation<double> _pulseAnim;

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    );
    _pulseAnim = Tween<double>(
      begin: 1.0,
      end: 1.5,
    ).animate(CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut));
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
      _pulseCtrl.stop();
      _pulseCtrl.reset();
      setState(() => _isRecording = false);
      _stopRecording();
    } else {
      setState(() {
        _isRecording = true;
        _elapsed = Duration.zero;
      });
      _pulseCtrl.repeat(reverse: true);
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
            const SizedBox(height: 12),
            AnimatedBuilder(
              animation: _pulseAnim,
              builder: (_, _) => SizedBox(
                width: 100,
                height: 100,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
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
            ),
          ],
        ),
      ),
    );
  }
}