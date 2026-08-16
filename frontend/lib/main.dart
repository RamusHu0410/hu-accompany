import 'package:flutter/material.dart';
import 'package:liquid_glass_easy/liquid_glass_easy.dart';
import 'Draggable_Recorder_Button.dart';
import 'Drawing_Overlay.dart';
import 'Music_Library_Page.dart';
import 'LiquidGlass.dart';
import 'Score_Page_Controller.dart';
import 'Score_Pages_View.dart';
import 'Record_Navigator_Page.dart';
import 'Vinyl_Loading_Screen.dart';
import 'dart:ffi' as ffi;
import 'dart:typed_data';
// CHANGED: the backend now returns a literal PDF instead of MusicXML, so
// the OSMD WebView renderer (Score_osmd_renderer.dart) no longer applies
// here — swapped for the swipeable PDF page view (Score_Pages_View.dart +
// Score_Page_Controller.dart). Note this drops the OSMD-based per-note
// wrong-note coloring feature (colorNotes/resetColors); there's no direct
// equivalent for a rasterized PDF page yet.

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

void main() {
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
      // App now opens onto the turntable navigator (Practice / Search /
      // Shelf, chosen by spinning a record) instead of dropping straight
      // into the score viewer. ScoreViewerPage is still reachable — it's
      // just one of the records on the platter now.
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
              // LAYER 1: PDF score pages (or placeholder background)
              if (_hasScore)
                Positioned.fill(
                  child: Score_Pages_View(
                    controller: _pageController!,
                  ),
                )
              else
                Positioned.fill(
                  child: Container(color: const Color.fromARGB(255, 255, 255, 255)),
                ),
              // LAYER 2: Drawing overlay
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
              // LAYER 3: Floating Toolbar
              Positioned(
                top: 16,
                right: 16,
                child: LiquidGlass(
                  borderRadius: BorderRadius.circular(30),
                  blur: 18,
                  tintOpacity: 0.14,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // Small "reveal pen settings" arrow — leads the row
                        // so it sits closest to (and points toward) the
                        // panel that pops out further left of the toolbar.
                        IconButton(
                          padding: EdgeInsets.zero,
                          constraints: const BoxConstraints(
                            minWidth: 28,
                            minHeight: 28,
                          ),
                          icon: Icon(
                            Icons.chevron_left,
                            size: 18,
                            color: _showPenSettings
                                ? const Color(0xFFE94560)
                                : const Color.fromARGB(255, 170, 170, 170),
                          ),
                          onPressed: () => setState(
                              () => _showPenSettings = !_showPenSettings),
                        ),
                        IconButton(
                          icon: Icon(
                            Icons.edit_outlined,
                            size: 22,
                            color: _isDrawingMode
                                ? const Color(0xFFE94560)
                                : const Color.fromARGB(255, 170, 170, 170),
                          ),
                          onPressed: () => setState(() {
                            _isDrawingMode = !_isDrawingMode;
                            // Pen and eraser are mutually exclusive tools.
                            if (_isDrawingMode) _isErasing = false;
                          }),
                        ),
                        IconButton(
                          icon: Icon(
                            Icons.backspace_outlined,
                            size: 20,
                            color: _isErasing
                                ? const Color(0xFFE94560)
                                : const Color.fromARGB(255, 170, 170, 170),
                          ),
                          onPressed: () => setState(() {
                            _isErasing = !_isErasing;
                            if (_isErasing) _isDrawingMode = false;
                          }),
                        ),
                      ],
                    ),
                  ),
                ),
              ),

              // LAYER 3b: Pen settings panel — pops out to the left of the
              // toolbar when the small arrow is tapped.
              if (_showPenSettings)
                Positioned(
                  top: 16,
                  right: 132,
                  child: LiquidGlass(
                    borderRadius: BorderRadius.circular(20),
                    blur: 18,
                    tintOpacity: 0.05,
                    child: Container(
                      width: 210,
                      padding: const EdgeInsets.all(14),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Text(
                            'Pen',
                            style: TextStyle(
                              color: Color.fromARGB(255, 170, 170, 170),
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          const SizedBox(height: 10),
                          // Color swatches
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: _penColorOptions.map((color) {
                              final bool selected = color.value == _penColor.value;
                              return GestureDetector(
                                onTap: () => setState(() => _penColor = color),
                                child: AnimatedContainer(
                                  duration: const Duration(milliseconds: 150),
                                  width: 26,
                                  height: 26,
                                  decoration: BoxDecoration(
                                    color: color,
                                    shape: BoxShape.circle,
                                    border: Border.all(
                                      color: selected
                                          ? Colors.white
                                          : Colors.transparent,
                                      width: 2,
                                    ),
                                    boxShadow: selected
                                        ? [
                                            BoxShadow(
                                              color: color.withOpacity(0.6),
                                              blurRadius: 6,
                                            ),
                                          ]
                                        : null,
                                  ),
                                ),
                              );
                            }).toList(),
                          ),
                          const SizedBox(height: 14),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Text(
                                'Size',
                                style: TextStyle(
                                  color: Color.fromARGB(255, 170, 170, 170),
                                  fontSize: 12,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              Text(
                                _penSize.toStringAsFixed(0),
                                style: const TextStyle(
                                  color: Color.fromARGB(255, 170, 170, 170),
                                  fontSize: 12,
                                ),
                              ),
                            ],
                          ),
                          SliderTheme(
                            data: SliderTheme.of(context).copyWith(
                              trackHeight: 3,
                              thumbShape: const RoundSliderThumbShape(
                                  enabledThumbRadius: 7),
                              overlayShape: const RoundSliderOverlayShape(
                                  overlayRadius: 14),
                              activeTrackColor: const Color(0xFFE94560),
                              inactiveTrackColor:
                                  const Color.fromARGB(60, 170, 170, 170),
                              thumbColor: const Color(0xFFE94560),
                            ),
                            child: Slider(
                              min: 1,
                              max: 14,
                              value: _penSize,
                              onChanged: (v) => setState(() => _penSize = v),
                            ),
                          ),
                          const SizedBox(height: 4),
                          // Texture — placeholder for a future update.
                          Opacity(
                            opacity: 0.4,
                            child: Row(
                              children: const [
                                Icon(Icons.texture, size: 16,
                                    color: Color.fromARGB(255, 170, 170, 170)),
                                SizedBox(width: 8),
                                Text(
                                  'Texture — coming soon',
                                  style: TextStyle(
                                    color: Color.fromARGB(255, 170, 170, 170),
                                    fontSize: 12,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),

              // LAYER 4: Draggable Recorder Button
              Draggable_Recorder_Button(
                onToggle: (isRecording) {
                  if (isRecording) {
                    _nativeBridge.startRecording();
                  } else {
                    _nativeBridge.stopRecording();
                  }
                },
              ),

              // LAYER 5: Nav Button
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
            ], // closes children of foreground Stack
          ), // closes foreground Stack (child:)
        ), // closes LiquidGlassView
      ), // closes SafeArea
    ); // closes Scaffold
  }
}