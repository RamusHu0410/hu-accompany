import 'dart:math';
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../theme/Color_Theme.dart';
import '../theme/Design_Tokens.dart';
import '../controllers/Disk_Spin_Controller.dart';
import '../widgets/Vinyl_Disk_Painter.dart';
import 'Shelf_Page.dart';
import 'Music_Library_Page.dart';
import 'Quiz_Home_Page.dart';
import '../main.dart';

/// One destination in the record crate — everything needed to draw its
/// disk and to build the page it opens once it's spun up to speed.
class _RecordEntry {
  final String title;
  final String sublabel;
  final Color diskColor;
  final WidgetBuilder pageBuilder;
  const _RecordEntry({
    required this.title,
    required this.sublabel,
    required this.pageBuilder,
    this.diskColor = TurntablePalette.diskPractice,
  });
}

/// Full-screen turntable navigator — the app's home screen. Swipe right to
/// left on the background to cue up the next record (Practice / Search /
/// Shelf); the old disk lifts off and the new one drops onto the platter,
/// like swapping a record by hand. A left-to-right drag is ignored — swaps
/// only ever move in one direction. Grab the loaded disk and spin it
/// clockwise and it keeps spinning with real momentum; spin it far enough
/// and the screen zooms into the label and blurs for a beat before opening
/// that page.
class Record_Navigator_Page extends StatefulWidget {
  const Record_Navigator_Page({super.key});

  @override
  State<Record_Navigator_Page> createState() => _Record_Navigator_PageState();
}

class _Record_Navigator_PageState extends State<Record_Navigator_Page>
    with TickerProviderStateMixin {
  late final List<_RecordEntry> _records = [
    _RecordEntry(
      title: 'PRACTICE',
      sublabel: 'your score',
      diskColor: TurntablePalette.diskPractice,
      pageBuilder: (_) => const ScoreViewerPage(),
    ),
    _RecordEntry(
      title: 'SEARCH',
      sublabel: 'the library',
      diskColor: TurntablePalette.diskSearch,
      pageBuilder: (_) => const Music_Library_Page(),
    ),
    _RecordEntry(
      title: 'SHELF',
      sublabel: 'saved scores',
      diskColor: TurntablePalette.diskShelf,
      pageBuilder: (_) => const Shelf_Page(),
    ),
    _RecordEntry(
      title: 'QUIZ',
      sublabel: 'theory & history',
      diskColor: TurntablePalette.diskQuiz,
      pageBuilder: (_) => const Quiz_Home_Page(),
    ),
  ];

  int _activeIndex = 0;
  int? _incomingIndex;

  /// 0..1, drives the disk-swap animation.
  ///
  /// A [ValueNotifier] rather than plain state: this changes on every frame
  /// of both the drag and the settle animation, and routing it through
  /// setState rebuilt the whole Stack — platter, tonearm, labels and dots —
  /// 60 times a second to move two disks. Only the disk layers listen now.
  final ValueNotifier<double> _swapProgress = ValueNotifier<double>(0);

  double _dragStartX = 0;
  bool _swiping = false;
  bool _launching = false;

  late final AnimationController _swapController;
  late final AnimationController _zoomController;

  @override
  void initState() {
    super.initState();
    _swapController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 420),
    );
    // Kept short and firm, per the "zooms in and blurs for half a second
    // or less" feel.
    _zoomController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 360),
    );
    // Registered once for the widget's lifetime. It used to be added on
    // every swap and removed from inside the callback, which stacked up
    // duplicate listeners whenever a settle was interrupted by a new drag.
    _swapController.addListener(_swapTick);
  }

  @override
  void dispose() {
    _swapController.removeListener(_swapTick);
    _swapController.dispose();
    _zoomController.dispose();
    _swapProgress.dispose();
    super.dispose();
  }

  void _onHorizontalDragStart(DragStartDetails d) {
    if (_launching) return;
    _dragStartX = d.globalPosition.dx;
    _swiping = true;
  }

  void _onHorizontalDragUpdate(DragUpdateDetails d) {
    if (!_swiping || _launching) return;
    final delta = d.globalPosition.dx - _dragStartX;

    // Only a right-to-left drag cues up the next record. A rightward drag
    // is ignored outright — no incoming disk, no progress — so it can't be
    // mistaken for a swap and doesn't compete with the disk's own spin
    // gesture for the touch.
    if (delta >= 0) {
      _swapProgress.value = 0;
      // Only the disappearance of the incoming disk needs a rebuild; the
      // progress reset above reaches the disk layers on its own.
      if (_incomingIndex != null) {
        setState(() => _incomingIndex = null);
      }
      return;
    }

    final width = MediaQuery.of(context).size.width;
    final next = (_activeIndex + 1) % _records.length;
    if (_incomingIndex != next) {
      setState(() => _incomingIndex = next);
    }
    _swapProgress.value = (delta.abs() / (width * 0.5)).clamp(0.0, 1.0);
  }

  void _onHorizontalDragEnd(DragEndDetails d) {
    if (!_swiping || _launching) return;
    _swiping = false;
    if (_swapProgress.value > 0.35 && _incomingIndex != null) {
      _completeSwap();
    } else {
      _cancelSwap();
    }
  }

  void _completeSwap() {
    HapticFeedback.selectionClick();
    _swapController.forward(from: _swapProgress.value).then((_) {
      if (!mounted) return;
      setState(() {
        _activeIndex = _incomingIndex!;
        _incomingIndex = null;
      });
      _swapProgress.value = 0;
      _swapController.value = 0;
    });
  }

  void _cancelSwap() {
    _swapController.reverse(from: _swapProgress.value).then((_) {
      if (!mounted) return;
      setState(() => _incomingIndex = null);
      _swapProgress.value = 0;
    });
  }

  void _swapTick() {
    if (!mounted) return;
    _swapProgress.value = _swapController.value;
  }

  Future<void> _onDiskActivated() async {
    if (_launching) return;
    _launching = true;
    HapticFeedback.mediumImpact();

    await _zoomController.forward(from: 0);
    if (!mounted) return;

    final entry = _records[_activeIndex];
    await Navigator.of(context).push(
      PageRouteBuilder(
        transitionDuration: Motion.slow,
        reverseTransitionDuration: Motion.base,
        pageBuilder: (_, _, _) => entry.pageBuilder(context),
        // The page settles in from slightly enlarged, continuing the
        // zoom the disk just performed rather than restarting the motion.
        transitionsBuilder: (_, anim, _, child) {
          final eased = CurvedAnimation(parent: anim, curve: Motion.enter);
          return FadeTransition(
            opacity: eased,
            child: ScaleTransition(
              scale: Tween<double>(begin: 1.06, end: 1.0).animate(eased),
              child: child,
            ),
          );
        },
      ),
    );

    if (!mounted) return;
    await _zoomController.reverse();
    _launching = false;
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    final diskSize = min(size.width, size.height) * 0.72;
    final current = _records[_activeIndex];
    final incoming = _incomingIndex != null ? _records[_incomingIndex!] : null;

    return Scaffold(
      backgroundColor: TurntablePalette.background,
      body: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onHorizontalDragStart: _onHorizontalDragStart,
        onHorizontalDragUpdate: _onHorizontalDragUpdate,
        onHorizontalDragEnd: _onHorizontalDragEnd,
        child: Stack(
          fit: StackFit.expand,
          children: [
            // Turntable mat
            Center(
              child: Container(
                width: diskSize + 40,
                height: diskSize + 40,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: TurntablePalette.mat,
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.5),
                      blurRadius: 40,
                      spreadRadius: 4,
                    ),
                  ],
                ),
              ),
            ),

            // Outgoing disk — lifts, tilts, and slides off the platter.
            if (incoming != null)
              _swapLayer(entry: current, diskSize: diskSize, outgoing: true),

            // Incoming disk (or the resting current disk when not swiping).
            _swapLayer(
              entry: incoming ?? current,
              diskSize: diskSize,
              outgoing: false,
              spinnable: incoming == null,
            ),

            // Tonearm resting at the edge of the platter.
            Positioned(
              top: size.height / 2 - diskSize / 2 - 30,
              right: size.width / 2 - diskSize / 2 - 10,
              child: _Tonearm(diskSize: diskSize),
            ),

            // Current page label
            Positioned(
              bottom: Space.xxl * 2,
              left: 0,
              right: 0,
              child: Column(
                children: [
                  Text(
                    current.title,
                    style: const TextStyle(
                      color: TurntablePalette.parchment,
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 3,
                    ),
                  ),
                  const SizedBox(height: Space.xs - 2),
                  Text(
                    'spin the record to open it',
                    style: TextStyle(
                      color: TurntablePalette.parchment.withValues(alpha: 0.4),
                      fontSize: 11,
                      letterSpacing: 0.5,
                    ),
                  ),
                ],
              ),
            ),

            // Which-record-is-loaded dots
            Positioned(
              top: Space.xl,
              left: 0,
              right: 0,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(_records.length, (i) {
                  final active = i == _activeIndex;
                  return AnimatedContainer(
                    duration: Motion.base,
                    curve: Motion.enter,
                    margin: const EdgeInsets.symmetric(horizontal: Space.xxs),
                    width: active ? 16 : 6,
                    height: 6,
                    decoration: BoxDecoration(
                      color: TurntablePalette.parchment.withValues(
                        alpha: active ? 0.85 : 0.25,
                      ),
                      borderRadius: BorderRadius.circular(3),
                    ),
                  );
                }),
              ),
            ),

            // Zoom + blur overlay played on activation — nothing rendered
            // at the very center on purpose; this is just the transition.
            AnimatedBuilder(
              animation: _zoomController,
              builder: (context, child) {
                final t = _zoomController.value;
                if (t == 0) return const SizedBox.shrink();
                return Positioned.fill(
                  child: BackdropFilter(
                    filter: ImageFilter.blur(sigmaX: 24 * t, sigmaY: 24 * t),
                    child: Container(
                      color: Colors.black.withValues(alpha: 0.35 * t),
                    ),
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _swapLayer({
    required _RecordEntry entry,
    required double diskSize,
    required bool outgoing,
    bool spinnable = false,
  }) {
    // The disk itself is built once and threaded through both builders as
    // `child`, so a swap frame only recomputes transforms — it never
    // rebuilds the record, its label or its spin gesture.
    final Widget disk = spinnable
        ? SpinnableDisk(
            size: diskSize,
            label: entry.title,
            sublabel: entry.sublabel,
            diskColor: entry.diskColor,
            onActivated: _onDiskActivated,
          )
        : VinylDisk(
            size: diskSize,
            rotation: 0,
            label: entry.title,
            sublabel: entry.sublabel,
            diskColor: entry.diskColor,
          );

    final zoomed = AnimatedBuilder(
      animation: _zoomController,
      child: disk,
      builder: (context, child) =>
          Transform.scale(scale: 1 + _zoomController.value * 2.4, child: child),
    );

    final bool swapInFlight = _incomingIndex != null;

    return Center(
      child: ValueListenableBuilder<double>(
        valueListenable: _swapProgress,
        child: zoomed,
        builder: (context, raw, child) {
          // At rest (no swap in flight) the "current" layer is treated as
          // fully arrived — progress: 1.0 — so it renders centered on the
          // platter instead of collapsing back to the off-screen
          // "incoming" pose.
          final progress = outgoing ? raw : (swapInFlight ? raw : 1.0);
          final dx = outgoing ? -progress * 260 : (1 - progress) * 260;
          final dy = outgoing ? -progress * 90 : (1 - progress) * 40;
          final scale = outgoing
              ? (1 - progress * 0.25)
              : (0.85 + progress * 0.15);
          final opacity = outgoing
              ? (1 - progress)
              : (progress == 0 ? 1.0 : progress);
          final rotationTilt = outgoing
              ? progress * 0.6
              : (1 - progress) * -0.5;

          return Transform.translate(
            offset: Offset(dx, dy),
            child: Transform.rotate(
              angle: rotationTilt,
              child: Transform.scale(
                scale: scale,
                child: Opacity(
                  opacity: opacity.clamp(0.0, 1.0),
                  child: child,
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _Tonearm extends StatelessWidget {
  final double diskSize;
  const _Tonearm({required this.diskSize});

  @override
  Widget build(BuildContext context) {
    final armLength = diskSize * 0.5;
    return SizedBox(
      width: armLength,
      height: armLength,
      child: CustomPaint(painter: _TonearmPainter()),
    );
  }
}

class _TonearmPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final base = Offset(size.width * 0.85, size.height * 0.15);
    final pivot = Offset(size.width * 0.55, size.height * 0.55);
    final tip = Offset(size.width * 0.15, size.height * 0.85);

    canvas.drawCircle(
      base,
      size.width * 0.09,
      Paint()..color = TurntablePalette.tonearmMount,
    );
    canvas.drawCircle(
      base,
      size.width * 0.09,
      Paint()
        ..color = Colors.white.withValues(alpha: 0.08)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5,
    );

    final armPaint = Paint()
      ..color = TurntablePalette.tonearmArm
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;
    canvas.drawLine(base, pivot, armPaint);
    canvas.drawLine(pivot, tip, armPaint);

    // Headshell + needle
    canvas.save();
    canvas.translate(tip.dx, tip.dy);
    canvas.rotate(-0.6);
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        const Rect.fromLTWH(-4, -10, 8, 20),
        const Radius.circular(3),
      ),
      Paint()..color = TurntablePalette.tonearmHead,
    );
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _TonearmPainter oldDelegate) => false;
}
