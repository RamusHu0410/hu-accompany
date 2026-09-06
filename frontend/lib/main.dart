import 'package:flutter/material.dart';
import 'Draggable_Recorder_Button.dart';
import 'Drawing_Overlay.dart';
import 'Music_Library_Page.dart';
import 'Score_Page_Controller.dart';
import 'Score_Pages_View.dart';
import 'dart:ffi' as ffi;
import 'dart:typed_data';
import 'Vinyl_Loading_Screen.dart';
import 'Record_Navigator_Page.dart';
import 'package:hu_accomponist/src/rust/frb_generated.dart';

typedef StartRecordingFunc = ffi.Void Function();
typedef StartRecordingFuncDart = void Function();
typedef StopRecordingFunc = ffi.Void Function();
typedef StopRecordingFuncDart = void Function();

// ─── Safe no-op stubs used when native symbols are unavailable ───────────────
void _stubStart() =>
    debugPrint('NativeBridge: start_recording stub (symbols not linked yet)');
void _stubStop() =>
    debugPrint('NativeBridge: stop_recording stub (symbols not linked yet)');

class NativeBridge {
  // Nullable so we know whether real lookup succeeded
  ffi.DynamicLibrary? _nativeLib;

  // Always callable — fall back to stubs if lookup failed
  StartRecordingFuncDart _startRecording = _stubStart;
  StopRecordingFuncDart _stopRecording = _stubStop;

  bool get isNativeAvailable => _nativeLib != null;

  NativeBridge() {
    // All lookup work is inside try/catch so a missing symbol
    // can NEVER reach main() and block the UI from rendering.
    try {
      final lib = ffi.DynamicLibrary.executable();

      _startRecording = lib
          .lookup<ffi.NativeFunction<StartRecordingFunc>>('start_recording')
          .asFunction();

      _stopRecording = lib
          .lookup<ffi.NativeFunction<StopRecordingFunc>>('stop_recording')
          .asFunction();

      _nativeLib = lib; // only set AFTER both lookups succeed
      debugPrint('NativeBridge: native symbols linked successfully.');
    } on ArgumentError catch (e) {
      // Symbol not found — app keeps running with stubs
      debugPrint('NativeBridge: symbol lookup failed — $e');
      debugPrint(
        'NativeBridge: running with no-op stubs. '
        'Make sure start_recording / stop_recording are compiled '
        'into the iOS Runner target with external "C" linkage.',
      );
    } catch (e) {
      debugPrint('NativeBridge: unexpected init error — $e');
    }
  }

  // Public API — callers never touch private fields directly
  void startRecording() => _startRecording();
  void stopRecording() => _stopRecording();
}

// Single shared instance — safe because constructor never throws now
final NativeBridge _nativeBridge = NativeBridge();

Future<void> main() async {
  // Attempt to load the native Rust library, but never let a failure here
  // block the UI from rendering — same reasoning as NativeBridge above.
  // Right now this is expected to potentially fail while the Xcode/cargokit
  // integration for native_ffi is still being fixed; once that's sorted,
  // this try/catch can stay as a permanent safety net regardless.
  try {
    await RustLib.init();
    debugPrint('RustLib: initialized successfully.');
  } catch (e) {
    debugPrint('RustLib: init failed — $e');
    debugPrint(
      'RustLib: continuing without Rust bindings. '
      'Any feature that calls into native_ffi will be unavailable '
      'until the native library is rebuilt/relinked.',
    );
  }

  runApp(const HuAccumponistApp());
}

class HuAccumponistApp extends StatelessWidget {
  const HuAccumponistApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.light,
        scaffoldBackgroundColor: const Color(0xFFF7F2E7),
        colorScheme: const ColorScheme.light(
          primary: Color(0xFF9A7A2C),
        ),
      ),
      // App now opens onto the vinyl spin-up splash and lands on the
      // turntable navigator (Practice / Search / Shelf, chosen by spinning
      // a record) instead of dropping straight into the score viewer.
      // ScoreViewerPage is still fully intact below — it's just one of the
      // records on the platter now (see Record_Navigator_Page.dart).
      home: const Vinyl_Loading_Screen(
        child: Record_Navigator_Page(),
      ),
    );
  }
}

class ScoreViewerPage extends StatefulWidget {
  final SelectedSheet? selected;
  const ScoreViewerPage({super.key, this.selected});

  @override
  State<ScoreViewerPage> createState() => _ScoreViewerPageState();
}

class _ScoreViewerPageState extends State<ScoreViewerPage> {
  bool _isDrawingMode = false;
  bool _isErasing = false;

  // Null until a sheet has been picked from the library.
  Uint8List? _pdfBytes;
  bool get _hasScore => _pdfBytes != null;

  // Owns the fetched-and-parsed pages for whatever score is currently
  // loaded — kept as a stable field (not rebuilt in build()) so it isn't
  // torn down and its cache/prefetch thrown away on every setState.
  ScorePageController? _pageController;

  // Swaps in a new score, or clears it if [pdfBytes] is null.
  void _setScore(Uint8List? pdfBytes) {
    _pdfBytes = pdfBytes;
    _pageController =
        pdfBytes != null ? ScorePageController(pdfBytes) : null;
  }

  @override
  void initState() {
    super.initState();

    // ASSUMPTION: SelectedSheet (defined in Music_Library_Page.dart) needs
    // a pdfBytes field now instead of musicXml, and whatever populates it
    // needs to call ApiService.fetchScorePdf() instead of the old
    // fetchMusicSheet().
    _setScore(widget.selected?.pdfBytes);
  }

  // Pen settings
  bool _showPenSettings = false;
  Color _penColor = const Color(0xFF9A7A2C);
  double _penSize = 3.0;

  static const List<Color> _penColorOptions = [
    Color(0xFF9A7A2C), // muted gold
    Color(0xFF30271F), // dark brown
    Color(0xFF5B7188), // muted blue
    Color(0xFF62765B), // muted green
    Color(0xFFB1844D), // warm amber
  ];

  void _goToNavPage() async {
    final selected = await Navigator.of(context).push<SelectedSheet>(
      PageRouteBuilder<SelectedSheet>(
        transitionDuration: const Duration(milliseconds: 400),
        pageBuilder: (context, animation, secondaryAnimation) =>
            const Music_Library_Page(),
        transitionsBuilder:
            (context, animation, secondaryAnimation, child) {
          final tween = Tween(
            begin: const Offset(0.0, 1.0),
            end: Offset.zero,
          ).chain(CurveTween(curve: Curves.easeOutCubic));

          return SlideTransition(
            position: animation.drive(tween),
            child: child,
          );
        },
      ),
    );

    if (selected != null) {
      setState(() {
        _setScore(selected.pdfBytes);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    const ivory = Color(0xFFF7F2E7);
    const paper = Color(0xFFFFFCF4);
    const brown = Color(0xFF30271F);
    const mutedBrown = Color(0xFF75695B);
    const gold = Color(0xFF9A7A2C);
    const lightGold = Color(0xFFD8C58D);

    return Scaffold(
      backgroundColor: ivory,
      body: SafeArea(
        child: Stack(
          children: [
            // ─────────────────────────────────────────────
            // CLEAN IVORY BACKGROUND
            // ─────────────────────────────────────────────
            Positioned.fill(
              child: Container(color: ivory),
            ),

            // Very subtle top border, matching the reference page.
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: Container(
                height: 1,
                color: lightGold.withValues(alpha: 0.35),
              ),
            ),

            // ─────────────────────────────────────────────
            // SCORE
            // ─────────────────────────────────────────────
            Positioned.fill(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(54, 54, 54, 58),
                child: Container(
                  decoration: BoxDecoration(
                    color: paper,
                    border: Border.all(
                      color: lightGold.withValues(alpha: 0.65),
                      width: 1,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: brown.withValues(alpha: 0.10),
                        blurRadius: 22,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  clipBehavior: Clip.antiAlias,
                  child: Stack(
                    children: [
                      if (_hasScore)
                        Positioned.fill(
                          child: Score_Pages_View(
                            controller: _pageController!,
                          ),
                        )
                      else
                        const Center(
                          child: Padding(
                            padding: EdgeInsets.all(30),
                            child: Text(
                              'Select a score from the library',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: mutedBrown,
                                fontSize: 15,
                                letterSpacing: 0.4,
                              ),
                            ),
                          ),
                        ),

                      // Small restrained ornament at the top of the score area.
                      Positioned(
                        top: 18,
                        left: 0,
                        right: 0,
                        child: IgnorePointer(
                          child: Center(
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Container(
                                  width: 38,
                                  height: 1,
                                  color: lightGold.withValues(alpha: 0.65),
                                ),
                                const SizedBox(width: 10),
                                Container(
                                  width: 7,
                                  height: 7,
                                  decoration: BoxDecoration(
                                    border: Border.all(
                                      color: gold.withValues(alpha: 0.75),
                                    ),
                                    shape: BoxShape.circle,
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Container(
                                  width: 38,
                                  height: 1,
                                  color: lightGold.withValues(alpha: 0.65),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),

            // ─────────────────────────────────────────────
            // DRAWING OVERLAY
            // ─────────────────────────────────────────────
            Positioned.fill(
              child: Drawing_Overlay(
                isDrawingMode: _isDrawingMode,
                isErasing: _isErasing,
                penColor: _penColor,
                penSize: _penSize,
              ),
            ),

            // ─────────────────────────────────────────────
            // TOP RIGHT TOOLS
            // ─────────────────────────────────────────────
            Positioned(
              top: 16,
              right: 22,
              child: Row(
                children: [
                  _ElegantToolButton(
                    icon: Icons.edit_outlined,
                    active: _isDrawingMode,
                    color: gold,
                    onTap: () {
                      setState(() {
                        _isDrawingMode = !_isDrawingMode;
                        if (_isDrawingMode) {
                          _isErasing = false;
                        }
                      });
                    },
                  ),
                  const SizedBox(width: 8),
                  _ElegantToolButton(
                    icon: Icons.auto_fix_normal_outlined,
                    active: _isErasing,
                    color: gold,
                    onTap: () {
                      setState(() {
                        _isErasing = !_isErasing;
                        if (_isErasing) {
                          _isDrawingMode = false;
                        }
                      });
                    },
                  ),
                  const SizedBox(width: 8),
                  _ElegantToolButton(
                    icon: Icons.palette_outlined,
                    active: _showPenSettings,
                    color: gold,
                    onTap: () {
                      setState(() {
                        _showPenSettings = !_showPenSettings;
                      });
                    },
                  ),
                ],
              ),
            ),

            // ─────────────────────────────────────────────
            // PEN SETTINGS
            // ─────────────────────────────────────────────
            if (_showPenSettings)
              Positioned(
                top: 68,
                right: 22,
                child: _ElegantPenPanel(
                  colors: _penColorOptions,
                  selectedColor: _penColor,
                  penSize: _penSize,
                  onColorSelected: (color) {
                    setState(() {
                      _penColor = color;
                    });
                  },
                  onSizeChanged: (size) {
                    setState(() {
                      _penSize = size;
                    });
                  },
                ),
              ),

            // ─────────────────────────────────────────────
            // ANIME MUSIC GIRL
            // ─────────────────────────────────────────────
            Positioned(
              right: 14,
              bottom: 4,
              child: IgnorePointer(
                child: SizedBox(
                  width: 145,
                  height: 175,
                  child: Image.asset(
                    'assets/images/wave.jpg',
                    fit: BoxFit.contain,
                  ),
                ),
              ),
            ),

            // ─────────────────────────────────────────────
            // SEARCH
            // ─────────────────────────────────────────────
            Positioned(
              left: 22,
              bottom: 20,
              child: _MinimalBottomButton(
                icon: Icons.search,
                color: mutedBrown,
                onTap: _goToNavPage,
              ),
            ),

            // ─────────────────────────────────────────────
            // EXIT
            // ─────────────────────────────────────────────
            Positioned(
              right: 22,
              bottom: 20,
              child: _MinimalBottomButton(
                icon: Icons.arrow_back,
                color: mutedBrown,
                onTap: () => Navigator.of(context).maybePop(),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ElegantToolButton extends StatelessWidget {
  final IconData icon;
  final bool active;
  final Color color;
  final VoidCallback onTap;

  const _ElegantToolButton({
    required this.icon,
    required this.active,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(30),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          width: 46,
          height: 46,
          decoration: BoxDecoration(
            color: active ? color : const Color(0xFFFFFCF4),
            shape: BoxShape.circle,
            border: Border.all(
              color: active ? color : const Color(0xFFD8C58D),
              width: 1,
            ),
            boxShadow: active
                ? [
                    BoxShadow(
                      color: color.withValues(alpha: 0.18),
                      blurRadius: 10,
                      offset: const Offset(0, 3),
                    ),
                  ]
                : null,
          ),
          child: Icon(
            icon,
            size: 20,
            color: active ? const Color(0xFFFFFCF4) : color,
          ),
        ),
      ),
    );
  }
}

class _ElegantPenPanel extends StatelessWidget {
  final List<Color> colors;
  final Color selectedColor;
  final double penSize;
  final ValueChanged<Color> onColorSelected;
  final ValueChanged<double> onSizeChanged;

  const _ElegantPenPanel({
    required this.colors,
    required this.selectedColor,
    required this.penSize,
    required this.onColorSelected,
    required this.onSizeChanged,
  });

  @override
  Widget build(BuildContext context) {
    const paper = Color(0xFFFFFCF4);
    const brown = Color(0xFF30271F);
    const gold = Color(0xFF9A7A2C);
    const lightGold = Color(0xFFD8C58D);

    return Container(
      width: 230,
      padding: const EdgeInsets.fromLTRB(18, 16, 18, 14),
      decoration: BoxDecoration(
        color: paper,
        border: Border.all(
          color: lightGold,
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: brown.withValues(alpha: 0.12),
            blurRadius: 18,
            offset: const Offset(0, 7),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'PEN',
            style: TextStyle(
              color: gold,
              fontSize: 10,
              letterSpacing: 2.5,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: colors.map((color) {
              final selected = color == selectedColor;

              return GestureDetector(
                onTap: () => onColorSelected(color),
                child: Container(
                  margin: const EdgeInsets.only(right: 10),
                  width: 25,
                  height: 25,
                  decoration: BoxDecoration(
                    color: color,
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: selected ? gold : Colors.transparent,
                      width: 2,
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 12),
          Container(
            height: 1,
            color: lightGold.withValues(alpha: 0.5),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              const Icon(
                Icons.line_weight,
                size: 15,
                color: gold,
              ),
              Expanded(
                child: SliderTheme(
                  data: SliderTheme.of(context).copyWith(
                    activeTrackColor: gold,
                    inactiveTrackColor:
                        lightGold.withValues(alpha: 0.45),
                    thumbColor: gold,
                    overlayColor: gold.withValues(alpha: 0.10),
                    trackHeight: 1,
                    thumbShape: const RoundSliderThumbShape(
                      enabledThumbRadius: 5,
                    ),
                  ),
                  child: Slider(
                    value: penSize,
                    min: 1,
                    max: 14,
                    onChanged: onSizeChanged,
                  ),
                ),
              ),
              SizedBox(
                width: 25,
                child: Text(
                  penSize.toStringAsFixed(1),
                  textAlign: TextAlign.right,
                  style: const TextStyle(
                    color: brown,
                    fontSize: 11,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _MinimalBottomButton extends StatelessWidget {
  final IconData icon;
  final Color color;
  final VoidCallback onTap;

  const _MinimalBottomButton({
    required this.icon,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(30),
        child: Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            color: const Color(0xFFFFFCF4),
            shape: BoxShape.circle,
            border: Border.all(
              color: const Color(0xFFD8C58D),
              width: 1,
            ),
          ),
          child: Icon(
            icon,
            size: 20,
            color: color,
          ),
        ),
      ),
    );
  }
}
