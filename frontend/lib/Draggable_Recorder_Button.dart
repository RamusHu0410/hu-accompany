import 'dart:async';
import 'package:flutter/material.dart';
import 'package:liquid_glass_easy/liquid_glass_easy.dart';

class Draggable_Recorder_Button extends StatefulWidget {
  final void Function(bool isRecording) onToggle;

  const Draggable_Recorder_Button({super.key, required this.onToggle});

  @override
  State<Draggable_Recorder_Button> createState() => _Draggable_Recorder_ButtonState();
}

class _Draggable_Recorder_ButtonState extends State<Draggable_Recorder_Button>
    with SingleTickerProviderStateMixin {
  bool _isRecording = false;
  Duration _elapsed = Duration.zero;
  Timer? _timer;
  Offset _position = const Offset(20, 400);

  // Approximate footprint of the whole draggable widget (label row +
  // spacing + the 100x100 icon stack) — used to keep it fully on-screen
  // when dragged, since Positioned won't clamp this for us.
  static const double _buttonWidth = 100.0;
  static const double _buttonHeight = 132.0;

  late final AnimationController _pulseCtrl;
  late final Animation<double> _pulseAnim;

  static const _idleColor  = Color(0xFF6C5CE7);
  static const _activeColor = Color(0xFFFF4757);

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    );
    _pulseAnim = Tween<double>(begin: 1.0, end: 1.5).animate(
      CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _timer?.cancel();
    _pulseCtrl.dispose();
    super.dispose();
  }

  void _toggle() {
    if (_isRecording) {
      _timer?.cancel();
      _pulseCtrl.stop();
      _pulseCtrl.reset();
      setState(() => _isRecording = false);
    } else {
      setState(() { _isRecording = true; _elapsed = Duration.zero; });
      _pulseCtrl.repeat(reverse: true);
      _timer = Timer.periodic(const Duration(seconds: 1), (_) {
        setState(() => _elapsed += const Duration(seconds: 1));
      });
    }
    widget.onToggle(_isRecording);
  }

  String get _elapsedLabel {
    final m = _elapsed.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = _elapsed.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  Widget _ring(Color color, double opacity) => Container(
    width: 80,
    height: 80,
    decoration: BoxDecoration(
      shape: BoxShape.circle,
      color: color.withValues(alpha: opacity),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final color = _isRecording ? _activeColor : _idleColor;

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
                  color: _isRecording ? const Color.fromARGB(255, 95, 95, 95) : const Color.fromARGB(137, 109, 109, 109),
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
                    if (_isRecording) ...[
                      Transform.scale(
                        scale: _pulseAnim.value,
                        child: _ring(_activeColor, 0.10),
                      ),
                      Transform.scale(
                        scale: (_pulseAnim.value + 1) / 2,
                        child: _ring(_activeColor, 0.18),
                      ),
                    ],
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
                            color: color.withValues(alpha: 0.45),
                            blurRadius: 20,
                            spreadRadius: 2,
                          ),
                        ],
                      ),
                      child: LiquidGlassLens(
                        style: LiquidGlassStyle(
                          shape: const LiquidGlassShape
                              .continuousRoundedRectangle(cornerRadius: 32),
                          appearance: LiquidGlassAppearance(
                            color: color.withValues(alpha: 0.55),
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
                              _isRecording ? Icons.stop_rounded : Icons.mic_rounded,
                              key: ValueKey(_isRecording),
                              color: const Color.fromARGB(255, 110, 110, 110),
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