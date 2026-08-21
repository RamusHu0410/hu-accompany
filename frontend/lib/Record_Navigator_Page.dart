import 'dart:math';
import 'dart:ui';
import 'package:flutter/material.dart';
import 'Disk_Spin_Controller.dart';
import 'Vinyl_Disk_Painter.dart';
import 'Shelf_Page.dart';
import 'Music_Library_Page.dart';
import 'main.dart';

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
    this.diskColor = const Color(0xFF0B0B0D),
  });
}

/// The three things a finger on the platter can be doing. Exactly one of
/// these is true at a time — there's no "maybe both", which is what let the
/// old two-GestureDetector setup fall out of sync (text updating without the
/// disk actually snapping into place).
enum _RecordState {
  /// A disk sits still on the platter — nothing is in progress. This is
  /// also the state while a fresh touch is still inside both deadzones and
  /// hasn't declared itself yet.
  locked,

  /// Mid-swipe: cueing up a different disk. Ends by snapping into [locked],
  /// either on the new disk or back on the old one.
  browsing,

  /// The locked disk is being spun (by finger or by its own free-spin decay)
  /// toward loading its page. Ends by settling back into [locked], or by
  /// firing the page navigation and then returning to [locked].
  spinning,
}

/// What an as-yet-undecided touch turns out to want, once it clears a
/// deadzone. Mirrors a joystick: small wiggles near center do nothing, and
/// whichever axis clears its own threshold first wins the whole gesture.
enum _GestureIntent { undecided, horizontal, spin }

/// Full-screen turntable navigator — the app's home screen. Swipe left or
/// right to cue up a different record (Practice / Search / Shelf); the old
/// disk lifts off and the new one drops onto the platter, like swapping a
/// record by hand. Grab the loaded disk and spin it and it keeps spinning
/// with real momentum; spin it far enough and the screen zooms into the
/// label and blurs for a beat before opening that page.
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
      diskColor: const Color(0xFF0B0B0D),
      pageBuilder: (_) => const ScoreViewerPage(),
    ),
    _RecordEntry(
      title: 'SEARCH',
      sublabel: 'the library',
      diskColor: const Color(0xFF16121A),
      pageBuilder: (_) => const Music_Library_Page(),
    ),
    _RecordEntry(
      title: 'SHELF',
      sublabel: 'saved scores',
      diskColor: const Color(0xFF12140F),
      pageBuilder: (_) => const Shelf_Page(),
    ),
  ];

  int _activeIndex = 0;
  int? _incomingIndex;
  double _swapProgress = 0; // 0..1, drives the disk-swap animation
  bool _launching = false;

  _RecordState _state = _RecordState.locked;
  late final DiskSpinController _spinController;

  late final AnimationController _swapController;
  late final AnimationController _zoomController;

  // --- Gesture arbitration state, valid only while a single pointer is
  // down. Deliberately not timer-based: everything here is resolved off of
  // accumulated movement, never elapsed time.
  int? _activePointer;
  _GestureIntent _intent = _GestureIntent.undecided;
  Offset _gestureOrigin = Offset.zero;
  double _gestureStartAngle = 0;
  double _dragBaseX = 0;
  Size _screenSize = Size.zero;

  // Small accidental finger movements are ignored until one of these is
  // cleared — like the dead zone on a joystick before a direction registers.
  static const double _horizontalDeadzonePx = 18;
  static const double _spinDeadzoneRadians = 0.35; // ~20°

  @override
  void initState() {
    super.initState();
    _spinController = DiskSpinController(
      vsync: this,
      onActivated: _onDiskActivated,
      onSettled: _onSpinSettled,
    );
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
  }

  @override
  void dispose() {
    _spinController.dispose();
    _swapController.dispose();
    _zoomController.dispose();
    super.dispose();
  }

  double _angleAt(Offset local) {
    final center = Offset(_screenSize.width / 2, _screenSize.height / 2);
    final d = local - center;
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

  // --- Unified pointer arbitration -----------------------------------
  //
  // One Listener for the whole platter, instead of a page-level
  // HorizontalDragGestureRecognizer racing a per-disk PanGestureRecognizer
  // in the gesture arena. Every touch starts "undecided": both a horizontal
  // swipe and a circular spin are candidates, each behind its own deadzone,
  // and whichever clears its deadzone first (proportionally) wins the touch
  // for its remaining duration. The other candidate is locked out.

  void _onPointerDown(PointerDownEvent event) {
    if (_launching || _activePointer != null) return;
    _activePointer = event.pointer;
    _intent = _GestureIntent.undecided;
    _gestureOrigin = event.localPosition;
    _gestureStartAngle = _angleAt(event.localPosition);

    // Touching the disk again (mid free-spin decay) stills it immediately,
    // like pressing a hand down on a real spinning record — the touch then
    // has to re-clear a deadzone to do anything new.
    _spinController.cancelDecay();
  }

  void _onPointerMove(PointerMoveEvent event) {
    if (event.pointer != _activePointer || _launching) return;
    final local = event.localPosition;

    if (_intent == _GestureIntent.undecided) {
      final dx = local.dx - _gestureOrigin.dx;
      final angle = _angleAt(local);
      final rotationDelta = _shortestDelta(_gestureStartAngle, angle);

      final horizontalReady = dx.abs() >= _horizontalDeadzonePx;
      final spinReady = rotationDelta.abs() >= _spinDeadzoneRadians;

      if (!horizontalReady && !spinReady) {
        return; // still inside both deadzones — ignore the wiggle
      }

      // Whichever axis is proportionally further past its own deadzone
      // claims the whole gesture.
      final horizontalRatio = dx.abs() / _horizontalDeadzonePx;
      final spinRatio = rotationDelta.abs() / _spinDeadzoneRadians;

      if (horizontalReady && (!spinReady || horizontalRatio >= spinRatio)) {
        _intent = _GestureIntent.horizontal;
        _beginBrowsing(local);
      } else {
        _intent = _GestureIntent.spin;
        _beginSpinning(angle);
      }
      return;
    }

    if (_intent == _GestureIntent.horizontal) {
      _updateBrowsing(local);
    } else if (_intent == _GestureIntent.spin) {
      _updateSpinning(local);
    }
  }

  void _onPointerUp(PointerEvent event) {
    if (event.pointer != _activePointer) return;
    _activePointer = null;
    if (_intent == _GestureIntent.horizontal) {
      _endBrowsing();
    } else if (_intent == _GestureIntent.spin) {
      _endSpinning();
    }
    _intent = _GestureIntent.undecided;
  }

  // --- Browsing (horizontal swipe between disks) ----------------------

  void _beginBrowsing(Offset local) {
    setState(() => _state = _RecordState.browsing);
    // Rebase to the point where the deadzone cleared, so the disk doesn't
    // jump by the deadzone's width the instant the swipe activates.
    _dragBaseX = local.dx;
  }

  void _updateBrowsing(Offset local) {
    final delta = local.dx - _dragBaseX;
    final dir = delta < 0 ? 1 : -1; // dragging left → cue up the next record
    _incomingIndex = (_activeIndex + dir) % _records.length;
    setState(() {
      _swapProgress = (delta.abs() / (_screenSize.width * 0.5)).clamp(0.0, 1.0);
    });
  }

  void _endBrowsing() {
    if (_swapProgress > 0.35 && _incomingIndex != null) {
      _completeSwap();
    } else {
      _cancelSwap();
    }
  }

  void _completeSwap() {
    _swapController.value = _swapProgress;
    _swapController.forward(from: _swapProgress).then((_) {
      if (!mounted) return;
      setState(() {
        _activeIndex = _incomingIndex!;
        _incomingIndex = null;
        _swapProgress = 0;
        _state = _RecordState.locked;
      });
      _swapController.value = 0;
      // A genuinely different record is now on the platter — it starts at
      // rest, physically locked, independent of whatever the last disk was
      // doing.
      _spinController.resetForNewDisk();
    });
    _swapController.addListener(_swapTick);
  }

  void _cancelSwap() {
    _swapController.value = _swapProgress;
    _swapController.reverse(from: _swapProgress).then((_) {
      if (!mounted) return;
      setState(() {
        _incomingIndex = null;
        _swapProgress = 0;
        _state = _RecordState.locked;
      });
    });
    _swapController.addListener(_swapTick);
  }

  void _swapTick() {
    if (!mounted) return;
    setState(() => _swapProgress = _swapController.value);
    if (_swapController.status == AnimationStatus.completed ||
        _swapController.status == AnimationStatus.dismissed) {
      _swapController.removeListener(_swapTick);
    }
  }

  // --- Spinning (circular drag on the locked disk) --------------------

  void _beginSpinning(double angle) {
    setState(() => _state = _RecordState.spinning);
    _spinController.start(angle);
  }

  void _updateSpinning(Offset local) {
    _spinController.update(_angleAt(local));
  }

  void _endSpinning() {
    // May kick off a friction-decay fling; _onSpinSettled or
    // _onDiskActivated will fire once that resolves.
    _spinController.end();
  }

  void _onSpinSettled() {
    if (!mounted || _launching) return;
    setState(() => _state = _RecordState.locked);
  }

  Future<void> _onDiskActivated() async {
    if (_launching) return;
    _launching = true;

    await _zoomController.forward(from: 0);
    if (!mounted) return;

    final entry = _records[_activeIndex];
    await Navigator.of(context).push(
      PageRouteBuilder(
        transitionDuration: const Duration(milliseconds: 250),
        pageBuilder: (_, __, ___) => entry.pageBuilder(context),
        transitionsBuilder: (_, anim, __, child) =>
            FadeTransition(opacity: anim, child: child),
      ),
    );

    if (!mounted) return;
    await _zoomController.reverse();
    setState(() => _state = _RecordState.locked);
    _launching = false;
  }

  @override
  Widget build(BuildContext context) {
    _screenSize = MediaQuery.of(context).size;
    final diskSize = min(_screenSize.width, _screenSize.height) * 0.72;
    final current = _records[_activeIndex];
    final incoming = _incomingIndex != null ? _records[_incomingIndex!] : null;

    return Scaffold(
      backgroundColor: const Color(0xFF1B1B1F),
      body: Listener(
        behavior: HitTestBehavior.opaque,
        onPointerDown: _onPointerDown,
        onPointerMove: _onPointerMove,
        onPointerUp: _onPointerUp,
        onPointerCancel: _onPointerUp,
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
                  color: const Color(0xFF232327),
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
              top: _screenSize.height / 2 - diskSize / 2 - 30,
              right: _screenSize.width / 2 - diskSize / 2 - 10,
              child: _Tonearm(diskSize: diskSize),
            ),

            // Current page label
            Positioned(
              bottom: 64,
              left: 0,
              right: 0,
              child: Column(
                children: [
                  Text(
                    current.title,
                    style: const TextStyle(
                      color: Color(0xFFEDE6DA),
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 3,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    _state == _RecordState.spinning
                        ? 'loading…'
                        : 'spin the record to open it',
                    style: TextStyle(
                      color: const Color(0xFFEDE6DA).withValues(alpha: 0.4),
                      fontSize: 11,
                      letterSpacing: 0.5,
                    ),
                  ),
                ],
              ),
            ),

            // Which-record-is-loaded dots
            Positioned(
              top: 24,
              left: 0,
              right: 0,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(_records.length, (i) {
                  final active = i == _activeIndex;
                  return AnimatedContainer(
                    duration: const Duration(milliseconds: 250),
                    margin: const EdgeInsets.symmetric(horizontal: 4),
                    width: active ? 16 : 6,
                    height: 6,
                    decoration: BoxDecoration(
                      color: const Color(0xFFEDE6DA)
                          .withValues(alpha: active ? 0.85 : 0.25),
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
                    child: Container(color: Colors.black.withValues(alpha: 0.35 * t)),
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
    final progress = outgoing ? _swapProgress : (_incomingIndex != null ? _swapProgress : 0.0);
    final dx = outgoing ? -progress * 260 : (1 - progress) * 260;
    final dy = outgoing ? -progress * 90 : (1 - progress) * 40;
    final scale = outgoing ? (1 - progress * 0.25) : (0.85 + progress * 0.15);
    final opacity = outgoing ? (1 - progress) : (progress == 0 ? 1.0 : progress);
    final rotationTilt = outgoing ? progress * 0.6 : (1 - progress) * -0.5;

    return Center(
      child: Transform.translate(
        offset: Offset(dx, dy),
        child: Transform.rotate(
          angle: rotationTilt,
          child: Transform.scale(
            scale: scale,
            child: Opacity(
              opacity: opacity.clamp(0.0, 1.0),
              child: AnimatedBuilder(
                animation: _zoomController,
                builder: (context, child) {
                  final t = _zoomController.value;
                  return Transform.scale(scale: 1 + t * 2.4, child: child);
                },
                child: spinnable
                    ? SpinningDisk(
                        controller: _spinController,
                        size: diskSize,
                        label: entry.title,
                        sublabel: entry.sublabel,
                        diskColor: entry.diskColor,
                      )
                    : VinylDisk(
                        size: diskSize,
                        rotation: 0,
                        label: entry.title,
                        sublabel: entry.sublabel,
                        diskColor: entry.diskColor,
                      ),
              ),
            ),
          ),
        ),
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

    canvas.drawCircle(base, size.width * 0.09, Paint()..color = const Color(0xFF2A2A2E));
    canvas.drawCircle(
      base,
      size.width * 0.09,
      Paint()
        ..color = Colors.white.withValues(alpha: 0.08)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5,
    );

    final armPaint = Paint()
      ..color = const Color(0xFFB9B9BD)
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
      Paint()..color = const Color(0xFF1E1E22),
    );
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _TonearmPainter oldDelegate) => false;
}
