import 'package:flutter/material.dart';
import 'Vinyl_Disk_Painter.dart';

/// Splash shown while the app boots — a small version of the same vinyl
/// disk used throughout the app, spinning at a constant rate. Swaps to
/// [child] once [minDuration] has elapsed.
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
  late final AnimationController _spin;
  bool _done = false;

  @override
  void initState() {
    super.initState();
    _spin = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat();
    Future.delayed(widget.minDuration, () {
      if (mounted) setState(() => _done = true);
    });
  }

  @override
  void dispose() {
    _spin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 400),
      child: _done
          ? widget.child
          : Container(
              key: const ValueKey('vinyl-loading'),
              color: const Color(0xFF1B1B1F),
              child: Center(
                child: AnimatedBuilder(
                  animation: _spin,
                  builder: (context, _) => VinylDisk(
                    size: 64,
                    rotation: _spin.value * 6.283185307179586,
                    label: '',
                    diskColor: const Color(0xFF0B0B0D),
                  ),
                ),
              ),
            ),
    );
  }
}
