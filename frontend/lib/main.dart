import 'package:flutter/material.dart';
import 'package:liquid_glass_easy/liquid_glass_easy.dart';
import 'Draggable_Recorder_Button.dart';
import 'Drawing_Overlay.dart';
import 'Music_Library_Page.dart';
import 'LiquidGlass.dart';
import 'Score_Page_Controller.dart';
import 'Score_Pages_View.dart';
import 'dart:ffi' as ffi;
import 'dart:typed_data';
// CHANGED: the backend now returns a literal PDF instead of MusicXML, so
// the OSMD WebView renderer (Score_osmd_renderer.dart) no longer applies
// here — swapped for the swipeable PDF page view (Score_Pages_View.dart +
// Score_Page_Controller.dart). Note this drops the OSMD-based per-note
// wrong-note coloring feature (colorNotes/resetColors); there's no direct
// equivalent for a rasterized PDF page yet.
import 'Vinyl_Loading_Screen.dart';
import 'Record_Navigator_Page.dart';
import 'Desk_Practice_Controls.dart';
import 'package:hu_accomponist/src/rust/frb_generated.dart';

typedef StartRecordingFunc = ffi.Void Function();
typedef StartRecordingFuncDart = void Function();
typedef StopRecordingFunc = ffi.Void Function();
typedef StopRecordingFuncDart = void Function();

// ─── Safe no-op stubs used when native symbols are unavailable ───────────────
void _stubStart() => debugPrint('NativeBridge: start_recording stub (symbols not linked yet)');
void _stubStop()  => debugPrint('NativeBridge: stop_recording stub (symbols not linked yet)');

class NativeBridge {
  // Nullable so we know whether real lookup succeeded
  ffi.DynamicLibrary? _nativeLib;

  // Always callable — fall back to stubs if lookup failed
  StartRecordingFuncDart _startRecording = _stubStart;
  StopRecordingFuncDart  _stopRecording  = _stubStop;

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
      debugPrint('NativeBridge: running with no-op stubs. '
          'Make sure start_recording / stop_recording are compiled '
          'into the iOS Runner target with external "C" linkage.');
    } catch (e) {
      debugPrint('NativeBridge: unexpected init error — $e');
    }
  }

  // Public API — callers never touch private fields directly
  void startRecording() => _startRecording();
  void stopRecording()  => _stopRecording();
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
    debugPrint('RustLib: continuing without Rust bindings. '
        'Any feature that calls into native_ffi will be unavailable '
        'until the native library is rebuilt/relinked.');
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
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color.fromARGB(255, 255, 255, 255),
        colorScheme: const ColorScheme.dark(primary: Color(0xFFE94560)),
      ),
      // App now opens onto the vinyl spin-up splash and lands on the
      // turntable navigator (Practice / Search / Shelf, chosen by spinning
      // a record) instead of dropping straight into the score viewer.
      // ScoreViewerPage is still fully intact below — it's just one of the
      // records on the platter now (see Record_Navigator_Page.dart).
      home: const Vinyl_Loading_Screen(child: Record_Navigator_Page()),
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
  // torn down and its cache/prefetch thrown away on every setState (e.g.
  // toggling pen color). Null alongside _pdfBytes until a sheet is picked.
  ScorePageController? _pageController;

  // Swaps in a new score, or clears it if [pdfBytes] is null.
  void _setScore(Uint8List? pdfBytes) {
    _pdfBytes = pdfBytes;
    _pageController = pdfBytes != null ? ScorePageController(pdfBytes) : null;
  }

  @override
  void initState() {
    super.initState();
    // ASSUMPTION: SelectedSheet (defined in Music_Library_Page.dart, not
    // reviewed here) needs a `pdfBytes` field now instead of `musicXml`,
    // and whatever populates it needs to call ApiService.fetchScorePdf()
    // instead of the old fetchMusicSheet(). Flag this to Ramus/update it
    // there too — this file alone can't fix that part.
    _setScore(widget.selected?.pdfBytes);
  }

  // Pen settings
  bool _showPenSettings = false;
  Color _penColor = const Color(0xFFE94560);
  double _penSize = 3.0;

  static const List<Color> _penColorOptions = [
    Color(0xFFE94560), // brand red/pink
    Color(0xFF2C2C2C), // near-black
    Color(0xFF2D6CDF), // blue
    Color(0xFF2FA84F), // green
    Color(0xFFF2A93B), // amber
  ];

  void _goToNavPage() async {
    final selected = await Navigator.of(context).push<SelectedSheet>(
      PageRouteBuilder<SelectedSheet>(
        transitionDuration: const Duration(milliseconds: 400),
        pageBuilder: (context, animation, secondaryAnimation) =>
            const Music_Library_Page(),
        transitionsBuilder: (context, animation, secondaryAnimation, child) {
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
    return Scaffold(
      body: SafeArea(
        child: LiquidGlassView(
          // Everything the glass buttons should refract goes here. This is
          // still rendered normally and stays fully interactive (e.g. the
          // Drawing_Overlay's gestures keep working) — it's just *also*
          // captured for the lenses on Skia backends like macOS desktop.
          backgroundWidget: Stack(
            children: [
              // LAYER 0: warm wooden desk backdrop — always present, the
              // "surface" everything else sits on.
              const Positioned.fill(child: WoodDeskBackground()),

              // LAYER 1: PDF score pages, framed like a sheet of paper
              // resting on the desk (or an empty desk when nothing's
              // loaded). Score_Pages_View itself is completely untouched.
              if (_hasScore)
                Positioned.fill(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(18, 28, 18, 28),
                    child: Container(
                      decoration: BoxDecoration(
                        color: const Color(0xFFFAF3E6),
                        borderRadius: BorderRadius.circular(4),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.45),
                            blurRadius: 24,
                            offset: const Offset(0, 10),
                          ),
                        ],
                      ),
                      clipBehavior: Clip.antiAlias,
                      child: Score_Pages_View(controller: _pageController!),
                    ),
                  ),
                )
              else
                const Positioned.fill(
                  child: Center(
                    child: Padding(
                      padding: EdgeInsets.symmetric(horizontal: 40),
                      child: Text(
                        'No score on the desk yet —\ntap the search button below to browse the library.',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: Color(0xCCFFF3E0),
                          fontSize: 14,
                          fontStyle: FontStyle.italic,
                          height: 1.5,
                        ),
                      ),
                    ),
                  ),
                ),

              // LAYER 2: Drawing overlay — unchanged.
              Positioned.fill(
                child: Drawing_Overlay(
                  isDrawingMode: _isDrawingMode,
                  isErasing: _isErasing,
                  penColor: _penColor,
                  penSize: _penSize,
                ),
              ),
            ],
          ), // closes Stack (backgroundWidget)

          child: Stack(
            children: [
              // LAYER 3: Pencil + eraser + palette toggle, sitting side by
              // side on the desk top-right — same three toggles as before
              // (_isDrawingMode / _isErasing / _showPenSettings), just
              // reskinned as physical objects instead of a glass toolbar.
              Positioned(
                top: 16,
                right: 16,
                child: Row(
                  children: [
                    PencilToolButton(
                      active: _isDrawingMode,
                      penColor: _penColor,
                      penSize: _penSize,
                      onTap: () => setState(() {
                        _isDrawingMode = !_isDrawingMode;
                        // Pen and eraser are still mutually exclusive.
                        if (_isDrawingMode) _isErasing = false;
                      }),
                    ),
                    const SizedBox(width: 10),
                    EraserToolButton(
                      active: _isErasing,
                      onTap: () => setState(() {
                        _isErasing = !_isErasing;
                        if (_isErasing) _isDrawingMode = false;
                      }),
                    ),
                    const SizedBox(width: 10),
                    PaintPaletteButton(
                      open: _showPenSettings,
                      currentColor: _penColor,
                      onTap: () => setState(
                        () => _showPenSettings = !_showPenSettings,
                      ),
                    ),
                  ],
                ),
              ),

              // LAYER 3b: Opened palette panel — same color-select and
              // size-select state/logic as before (_penColor, _penSize),
              // now a wooden palette board with paint blobs and a wooden
              // ruler instead of a glass swatch row and a Slider.
              if (_showPenSettings)
                Positioned(
                  top: 76,
                  right: 16,
                  child: PaintPalettePanel(
                    colors: _penColorOptions,
                    selected: _penColor,
                    onSelect: (c) => setState(() => _penColor = c),
                    penSize: _penSize,
                    minSize: 1,
                    maxSize: 14,
                    onSizeChanged: (v) => setState(() => _penSize = v),
                  ),
                ),

              // LAYER 4: Draggable Recorder Button — untouched.
              Draggable_Recorder_Button(
                onToggle: (isRecording) {
                  if (isRecording) {
                    _nativeBridge.startRecording();
                  } else {
                    _nativeBridge.stopRecording();
                  }
                },
              ),

              // LAYER 5: Search. Reliable free-form handwriting/gesture
              // recognition (drawing a "?" or writing "search" to
              // navigate) isn't practical to build without a proper
              // handwriting-recognition/ML library and real training —
              // a hand-rolled heuristic would misfire constantly against
              // the same canvas the drawing tool uses. Keeping the
              // existing, reliable tap target instead, per the fallback
              // — just reskinned to sit on the desk.
              Positioned(
                bottom: 32,
                left: 16,
                child: GestureDetector(
                  onTap: _goToNavPage,
                  child: LiquidGlass(
                    borderRadius: BorderRadius.circular(16),
                    blur: 14,
                    tintOpacity: 0.14,
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Icon(
                        Icons.search,
                        color: const Color.fromARGB(255, 170, 170, 170),
                      ),
                    ),
                  ),
                ),
              ),

              // LAYER 6: Exit — new physical push-button to leave
              // Practice and pop back to wherever it was opened from
              // (the turntable navigator).
              Positioned(
                bottom: 32,
                right: 16,
                child: DeskExitButton(
                  onTap: () => Navigator.of(context).maybePop(),
                ),
              ),
            ], // closes children of foreground Stack
          ), // closes foreground Stack (child:)
        ), // closes LiquidGlassView
      ), // closes SafeArea
    ); // closes Scaffold
  }
}