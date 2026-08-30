import 'dart:math';
import 'package:flutter/material.dart';

/// A warm, procedurally-painted wood desk surface — the backdrop for the
/// Practice page. No image asset needed: a gradient base plus seeded,
/// gently-curved grain lines, in the same procedural-painting spirit as
/// VinylDisk's groove rendering elsewhere in the app.
class WoodDeskBackground extends StatelessWidget {
  const WoodDeskBackground({super.key});

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: _WoodGrainPainter(),
      child: const SizedBox.expand(),
    );
  }
}

class _WoodGrainPainter extends CustomPainter {
  // Seeded so the grain pattern is stable across rebuilds/frames.
  static final Random _rng = Random(7);

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;

    final base = Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [Color(0xFF8B5A2B), Color(0xFF6B4226), Color(0xFF5A3820)],
      ).createShader(rect);
    canvas.drawRect(rect, base);

    for (int i = 0; i < 22; i++) {
      final y = _rng.nextDouble() * size.height;
      final amplitude = 6 + _rng.nextDouble() * 14;
      final path = Path()..moveTo(0, y);
      for (double x = 0; x <= size.width; x += size.width / 8) {
        final wobble = sin((x / size.width) * pi * 2 + i) * amplitude;
        path.lineTo(x, y + wobble);
      }
      canvas.drawPath(
        path,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 0.8 + _rng.nextDouble() * 1.4
          ..color = Colors.black.withValues(
            alpha: 0.06 + _rng.nextDouble() * 0.05,
          ),
      );
    }

    // Subtle vignette so the edges read as slightly darker, like light
    // falling on a real desk.
    canvas.drawRect(
      rect,
      Paint()
        ..shader = RadialGradient(
          center: Alignment.center,
          radius: 1.1,
          colors: [Colors.transparent, Colors.black.withValues(alpha: 0.28)],
        ).createShader(rect),
    );
  }

  @override
  bool shouldRepaint(covariant _WoodGrainPainter oldDelegate) => false;
}

/// The drawing-mode toggle, drawn as a real pencil lying at an angle. Its
/// graphite tip visually thickens with [penSize] and tints toward
/// [penColor], and it lifts (glow + straightens slightly) when drawing
/// mode is active. Tapping behaves exactly like the old edit icon button.
class PencilToolButton extends StatelessWidget {
  final bool active;
  final Color penColor;
  final double penSize;
  final VoidCallback onTap;

  const PencilToolButton({
    super.key,
    required this.active,
    required this.penColor,
    required this.penSize,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOut,
        padding: const EdgeInsets.all(6),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(10),
          boxShadow: active
              ? [
                  BoxShadow(
                    color: penColor.withValues(alpha: 0.55),
                    blurRadius: 14,
                    spreadRadius: 1,
                  ),
                ]
              : [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.35),
                    blurRadius: 6,
                    offset: const Offset(0, 3),
                  ),
                ],
        ),
        child: Transform.rotate(
          angle: active ? -0.05 : -0.35,
          child: CustomPaint(
            size: const Size(52, 52),
            painter: _PencilPainter(tipColor: penColor, tipWidth: penSize),
          ),
        ),
      ),
    );
  }
}

class _PencilPainter extends CustomPainter {
  final Color tipColor;
  final double tipWidth;
  _PencilPainter({required this.tipColor, required this.tipWidth});

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.translate(size.width / 2, size.height / 2);
    canvas.rotate(pi / 4);

    const bodyLength = 34.0;
    const bodyWidth = 9.0;

    final bodyRect = Rect.fromCenter(
      center: const Offset(-4, 0),
      width: bodyLength,
      height: bodyWidth,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(bodyRect, const Radius.circular(2)),
      Paint()..color = const Color(0xFFE0A85C),
    );
    canvas.drawRect(
      Rect.fromCenter(
        center: const Offset(-4 - bodyLength / 2 + 3, 0),
        width: 6,
        height: bodyWidth,
      ),
      Paint()..color = const Color(0xFFC9A227),
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromCenter(
          center: const Offset(-4 - bodyLength / 2 - 2, 0),
          width: 6,
          height: bodyWidth,
        ),
        const Radius.circular(3),
      ),
      Paint()..color = const Color(0xFFE58B8B),
    );

    // Tip cone — graphite width scales with tipWidth, so the pencil
    // visually reflects the current stroke thickness at a glance.
    final tipStart = -4 + bodyLength / 2;
    const tipLen = 12.0;
    final halfW = (bodyWidth / 2).clamp(2.0, 6.0);
    final graphiteHalf = (tipWidth / 2).clamp(0.8, halfW - 1);
    final tipPath = Path()
      ..moveTo(tipStart, -halfW)
      ..lineTo(tipStart + tipLen - 4, -graphiteHalf)
      ..lineTo(tipStart + tipLen, 0)
      ..lineTo(tipStart + tipLen - 4, graphiteHalf)
      ..lineTo(tipStart, halfW)
      ..close();
    canvas.drawPath(tipPath, Paint()..color = const Color(0xFFF4D9A0));

    final graphitePath = Path()
      ..moveTo(tipStart + tipLen - 4, -graphiteHalf)
      ..lineTo(tipStart + tipLen, 0)
      ..lineTo(tipStart + tipLen - 4, graphiteHalf)
      ..close();
    canvas.drawPath(
      graphitePath,
      Paint()..color = tipColor.withValues(alpha: 0.9),
    );

    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _PencilPainter oldDelegate) =>
      oldDelegate.tipColor != tipColor || oldDelegate.tipWidth != tipWidth;
}

/// The eraser-mode toggle — a small pink drafting-eraser block. Tapping
/// behaves exactly like the old backspace icon button.
class EraserToolButton extends StatelessWidget {
  final bool active;
  final VoidCallback onTap;
  const EraserToolButton({
    super.key,
    required this.active,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(10),
          boxShadow: [
            BoxShadow(
              color: active
                  ? const Color(0xFFE94560).withValues(alpha: 0.5)
                  : Colors.black.withValues(alpha: 0.3),
              blurRadius: active ? 14 : 6,
              offset: const Offset(0, 3),
            ),
          ],
        ),
        child: Transform.rotate(
          angle: -0.35,
          child: Container(
            width: 30,
            height: 18,
            decoration: BoxDecoration(
              color: active
                  ? const Color(0xFFFF8FA3)
                  : const Color(0xFFE58B8B),
              borderRadius: BorderRadius.circular(4),
              border: Border.all(color: const Color(0xFFB35F5F), width: 1.2),
            ),
          ),
        ),
      ),
    );
  }
}

/// Collapsed toggle for the color panel — a small artist's palette icon
/// tinted to hint at the currently-selected color. Tapping behaves exactly
/// like the old "reveal pen settings" chevron did.
class PaintPaletteButton extends StatelessWidget {
  final bool open;
  final Color currentColor;
  final VoidCallback onTap;

  const PaintPaletteButton({
    super.key,
    required this.open,
    required this.currentColor,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(10),
          boxShadow: [
            BoxShadow(
              color: open
                  ? currentColor.withValues(alpha: 0.5)
                  : Colors.black.withValues(alpha: 0.3),
              blurRadius: open ? 14 : 6,
              offset: const Offset(0, 3),
            ),
          ],
        ),
        child: SizedBox(
          width: 40,
          height: 34,
          child: CustomPaint(
            painter: _MiniPaletteIconPainter(highlight: currentColor),
          ),
        ),
      ),
    );
  }
}

class _MiniPaletteIconPainter extends CustomPainter {
  final Color highlight;
  _MiniPaletteIconPainter({required this.highlight});

  @override
  void paint(Canvas canvas, Size size) {
    final boardRect = Rect.fromLTWH(0, 4, size.width, size.height - 4);
    final boardPath = Path()..addOval(boardRect);
    canvas.drawPath(boardPath, Paint()..color = const Color(0xFFD2B48C));
    canvas.drawPath(
      boardPath,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.2
        ..color = const Color(0xFF8B5A2B),
    );
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(size.width * 0.72, size.height * 0.62),
        width: 8,
        height: 6,
      ),
      Paint()..color = const Color(0xFF5A3820).withValues(alpha: 0.7),
    );

    final blobColors = [
      highlight,
      const Color(0xFF2D6CDF),
      const Color(0xFF2FA84F),
      const Color(0xFFF2A93B),
    ];
    for (int i = 0; i < blobColors.length; i++) {
      final angle = -0.6 + i * 0.5;
      final dx = size.width * 0.35 + cos(angle) * size.width * 0.28;
      final dy = size.height * 0.55 + sin(angle) * size.height * 0.35;
      canvas.drawCircle(Offset(dx, dy), 3.4, Paint()..color = blobColors[i]);
    }
  }

  @override
  bool shouldRepaint(covariant _MiniPaletteIconPainter oldDelegate) =>
      oldDelegate.highlight != highlight;
}

/// The expanded color + thickness panel — a wooden palette board with
/// clickable paint blobs (replaces the old swatch row) plus a wooden ruler
/// for pencil thickness (replaces the old Slider). Reuses the same
/// [colors]/[selected]/[onSelect] contract the old swatch row used, and the
/// same min/max/value/onChanged contract the old Slider used — this widget
/// only changes how those are drawn and interacted with.
class PaintPalettePanel extends StatelessWidget {
  final List<Color> colors;
  final Color selected;
  final ValueChanged<Color> onSelect;
  final double penSize;
  final double minSize;
  final double maxSize;
  final ValueChanged<double> onSizeChanged;

  const PaintPalettePanel({
    super.key,
    required this.colors,
    required this.selected,
    required this.onSelect,
    required this.penSize,
    required this.minSize,
    required this.maxSize,
    required this.onSizeChanged,
  });

  List<Offset> _blobPositions(int count) {
    final positions = <Offset>[];
    const centerX = 95.0;
    const centerY = 45.0;
    const radiusX = 80.0;
    const radiusY = 32.0;
    for (int i = 0; i < count; i++) {
      final t = count <= 1 ? 0.5 : i / (count - 1);
      final angle = pi * 0.15 + t * pi * 0.7;
      positions.add(
        Offset(
          centerX - cos(angle) * radiusX,
          centerY - sin(angle) * radiusY - 6,
        ),
      );
    }
    return positions;
  }

  @override
  Widget build(BuildContext context) {
    final positions = _blobPositions(colors.length);
    return Container(
      width: 220,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF6B4226),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: const Color(0xFF3E2723), width: 2),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.4),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text(
            'PALETTE',
            style: TextStyle(
              color: Color(0xFFEDE0C8),
              fontSize: 11,
              fontWeight: FontWeight.w700,
              letterSpacing: 2,
            ),
          ),
          const SizedBox(height: 10),
          SizedBox(
            height: 90,
            child: Stack(
              children: [
                Positioned.fill(
                  child: CustomPaint(painter: _PaletteBoardPainter()),
                ),
                for (int i = 0; i < colors.length; i++)
                  Positioned(
                    left: positions[i].dx - 12,
                    top: positions[i].dy - 12,
                    child: GestureDetector(
                      onTap: () => onSelect(colors[i]),
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 150),
                        width: 24,
                        height: 24,
                        decoration: BoxDecoration(
                          color: colors[i],
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: colors[i] == selected
                                ? Colors.white
                                : Colors.black.withValues(alpha: 0.25),
                            width: colors[i] == selected ? 2.5 : 1,
                          ),
                          boxShadow: colors[i] == selected
                              ? [
                                  BoxShadow(
                                    color: colors[i].withValues(alpha: 0.7),
                                    blurRadius: 8,
                                  ),
                                ]
                              : [
                                  BoxShadow(
                                    color: Colors.black.withValues(
                                      alpha: 0.3,
                                    ),
                                    blurRadius: 3,
                                    offset: const Offset(0, 1),
                                  ),
                                ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'THICKNESS',
                style: TextStyle(
                  color: Color(0xFFEDE0C8),
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.5,
                ),
              ),
              Text(
                penSize.toStringAsFixed(0),
                style: const TextStyle(
                  color: Color(0xFFEDE0C8),
                  fontSize: 12,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          WoodenRulerSlider(
            value: penSize,
            min: minSize,
            max: maxSize,
            onChanged: onSizeChanged,
          ),
        ],
      ),
    );
  }
}

class _PaletteBoardPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final rect = Rect.fromLTWH(0, 0, size.width, size.height);
    final path = Path()..addOval(rect.deflate(2));
    canvas.drawShadow(path, Colors.black, 4, false);
    canvas.drawPath(path, Paint()..color = const Color(0xFFD2B48C));
    canvas.drawPath(
      path,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..color = const Color(0xFF8B5A2B),
    );
    final hole = Rect.fromCenter(
      center: Offset(size.width * 0.78, size.height * 0.78),
      width: 26,
      height: 16,
    );
    canvas.drawOval(hole, Paint()..color = const Color(0xFF5A3820));
    canvas.drawOval(
      hole,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1
        ..color = Colors.black.withValues(alpha: 0.4),
    );
  }

  @override
  bool shouldRepaint(covariant _PaletteBoardPainter oldDelegate) => false;
}

/// A small wooden ruler that drags horizontally to set pencil thickness.
/// Further left = thinner, further right = thicker — a drop-in visual
/// replacement for the old Slider with the same value/min/max/onChanged
/// contract.
class WoodenRulerSlider extends StatelessWidget {
  final double value;
  final double min;
  final double max;
  final ValueChanged<double> onChanged;

  const WoodenRulerSlider({
    super.key,
    required this.value,
    required this.min,
    required this.max,
    required this.onChanged,
  });

  void _updateFromLocalX(double localX, double width) {
    final t = (localX / width).clamp(0.0, 1.0);
    onChanged(min + t * (max - min));
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        final t = ((value - min) / (max - min)).clamp(0.0, 1.0);
        return GestureDetector(
          onPanStart: (d) => _updateFromLocalX(d.localPosition.dx, width),
          onPanUpdate: (d) => _updateFromLocalX(d.localPosition.dx, width),
          onTapDown: (d) => _updateFromLocalX(d.localPosition.dx, width),
          child: SizedBox(
            height: 40,
            width: width,
            child: Stack(
              clipBehavior: Clip.none,
              children: [
                Positioned.fill(child: CustomPaint(painter: _RulerPainter())),
                Positioned(
                  left: (t * (width - 18)).clamp(0.0, width - 18),
                  top: -6,
                  child: Container(
                    width: 18,
                    height: 46,
                    decoration: BoxDecoration(
                      color: const Color(0xFFC9A227),
                      borderRadius: BorderRadius.circular(3),
                      border: Border.all(
                        color: const Color(0xFF8A6E1B),
                        width: 1.5,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.4),
                          blurRadius: 4,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _RulerPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final track = RRect.fromRectAndRadius(
      Rect.fromLTWH(0, 10, size.width, 18),
      const Radius.circular(3),
    );
    canvas.drawRRect(track, Paint()..color = const Color(0xFFC49A6C));
    canvas.drawRRect(
      track,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5
        ..color = const Color(0xFF8B5A2B),
    );

    const tickCount = 13;
    for (int i = 0; i <= tickCount; i++) {
      final x = size.width * i / tickCount;
      final isMajor = i % 3 == 0;
      canvas.drawLine(
        Offset(x, 10),
        Offset(x, isMajor ? 26 : 20),
        Paint()
          ..strokeWidth = isMajor ? 1.4 : 0.8
          ..color = const Color(0xFF5A3820).withValues(
            alpha: isMajor ? 0.8 : 0.5,
          ),
      );
    }
  }

  @override
  bool shouldRepaint(covariant _RulerPainter oldDelegate) => false;
}

/// A physical-looking push button to leave Practice — a recessed red
/// button set into a dark bezel, like something bolted to the edge of the
/// desk. [onTap] is the caller's exit action (e.g. Navigator.pop).
class DeskExitButton extends StatelessWidget {
  final VoidCallback onTap;
  const DeskExitButton({super.key, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 60,
        height: 60,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: const Color(0xFF3E2723),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.45),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        padding: const EdgeInsets.all(6),
        child: Container(
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: const RadialGradient(
              center: Alignment(-0.3, -0.3),
              colors: [Color(0xFFE05C5C), Color(0xFFB33A3A)],
            ),
            border: Border.all(color: const Color(0xFF7A2323), width: 2),
          ),
          child: const Center(
            child: Text(
              'EXIT',
              style: TextStyle(
                color: Colors.white,
                fontSize: 10,
                fontWeight: FontWeight.w800,
                letterSpacing: 1,
              ),
            ),
          ),
        ),
      ),
    );
  }
}