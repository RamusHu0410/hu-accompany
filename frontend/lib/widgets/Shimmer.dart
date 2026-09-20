import 'package:flutter/material.dart';
import '../theme/Design_Tokens.dart';

/// Sweeps a soft highlight across everything below it.
///
/// Deliberately wraps a whole skeleton subtree rather than each placeholder:
/// one [ShaderMask] costs a single `saveLayer` and one ticking controller no
/// matter how many boxes are underneath, whereas a per-box shimmer pays both
/// costs per tile and the sweeps drift out of phase with each other.
class Shimmer extends StatefulWidget {
  final Widget child;

  /// The resting tone of the placeholders underneath.
  final Color base;

  /// The moving highlight. Should be a near-neighbour of [base] — a wide
  /// gap reads as a flash rather than a sheen.
  final Color highlight;

  const Shimmer({
    super.key,
    required this.child,
    required this.base,
    required this.highlight,
  });

  @override
  State<Shimmer> createState() => _ShimmerState();
}

class _ShimmerState extends State<Shimmer>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      // The subtree is passed through as `child` so it is built once and
      // only the mask is rebuilt on each tick.
      child: widget.child,
      builder: (context, child) {
        final t = _controller.value;
        return ShaderMask(
          blendMode: BlendMode.srcATop,
          shaderCallback: (bounds) => LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [widget.base, widget.highlight, widget.base],
            stops: const [0.0, 0.5, 1.0],
            transform: _SlideGradient(t),
          ).createShader(bounds),
          child: child,
        );
      },
    );
  }
}

/// Slides the gradient from fully off one edge to fully off the other, so
/// the sheen enters and leaves rather than popping at the wrap point.
class _SlideGradient extends GradientTransform {
  final double t;
  const _SlideGradient(this.t);

  @override
  Matrix4 transform(Rect bounds, {TextDirection? textDirection}) {
    return Matrix4.translationValues(bounds.width * (t * 2 - 1), 0, 0);
  }
}

/// A single placeholder block. Const-constructible so a skeleton tree costs
/// nothing to rebuild.
class SkeletonBox extends StatelessWidget {
  final double? width;
  final double height;
  final BorderRadius borderRadius;

  const SkeletonBox({
    super.key,
    this.width,
    required this.height,
    this.borderRadius = Radii.cardRadius,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        // Any opaque colour works — the shimmer above repaints it via
        // srcATop; only the alpha of these pixels matters.
        color: Colors.white,
        borderRadius: borderRadius,
      ),
    );
  }
}
