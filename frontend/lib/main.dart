import 'package:flutter/material.dart';
import 'widgets/Draggable_Recorder_Button.dart';
import 'widgets/Drawing_Overlay.dart';
import 'screens/Music_Library_Page.dart';
import 'models/Score_Page_Controller.dart';
import 'renderers/Score_Pages_View.dart';
import 'dart:ffi' as ffi;
import 'dart:typed_data';
import 'screens/Vinyl_Loading_Screen.dart';
import 'screens/Record_Navigator_Page.dart';
import 'package:hu_accomponist/src/rust/frb_generated.dart';
import 'package:hu_accomponist/src/rust/models.dart';
import 'services/Phrase_Send2_Server.dart';
import 'utils/Pull_back_Phrase.dart';
import 'models/Phrase_Feedback.dart';
import 'theme/Color_Theme.dart';
import 'theme/Design_Tokens.dart';
import 'widgets/Practice_Tool_Buttons.dart';
import 'widgets/Practice_Pen_Panel.dart';
import 'widgets/Practice_Settings_Drawer.dart';

// Re-exported so anything that already reached for PhraseFeedback through
// main.dart keeps compiling after the enum moved to its own file.
export 'models/Phrase_Feedback.dart';




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
// NOTE: AudioNative (raw dart:ffi start_recording/stop_recording) is no
// longer wired in here — recording now goes through Draggable_Recorder_Button,
// which owns the Rust-bridge notesStream() pipeline directly. AudioNative
// and NativeBridge above are both now unused by this flow; left in place
// in case you still want them, but worth deleting if not.

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
        scaffoldBackgroundColor: PracticePalette.ivory,
        colorScheme: const ColorScheme.light(
          primary: PracticePalette.gold,
        ),
        // Every platform's default route animation is replaced with one
        // fade-through, so moving between screens feels like the same app
        // regardless of which device it is running on.
        pageTransitionsTheme: const PageTransitionsTheme(
          builders: {
            TargetPlatform.iOS: FadeForwardsPageTransitionsBuilder(),
            TargetPlatform.android: FadeForwardsPageTransitionsBuilder(),
            TargetPlatform.macOS: FadeForwardsPageTransitionsBuilder(),
          },
        ),
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
  final _scaffoldKey = GlobalKey<ScaffoldState>();

  bool _isDrawingMode = false;
  bool _isErasing = false;
  bool _isRecording = false;

  PhraseFeedback _feedback = PhraseFeedback.none;
  final DrawingController _drawing = DrawingController();

  /// Call this from the Flutter-Rust-Bridge performance-result callback.
  void setPhraseFeedback(PhraseFeedback feedback) {
    if (!mounted) return;
    setState(() => _feedback = feedback);
  }

  /// Convenience entry point for a Rust result that reports whether a note
  /// was correct. Replace the bool with the Rust result type when it is wired
  /// into Flutter-Rust-Bridge.
  void applyPerformanceResult({required bool playedCorrectly}) {
    setPhraseFeedback(
      playedCorrectly ? PhraseFeedback.good : PhraseFeedback.off,
    );
  }

  void _onRecordingChanged(bool isRecording) {
    if (mounted) {
      setState(() => _isRecording = isRecording);
    }
    if (isRecording) {
      // A fresh recording gets a fresh session — the backend assigns the
      // real session id on phrase 1's response (see below).
      _feedbackSessionId = null;
      setPhraseFeedback(PhraseFeedback.none);
    }
  }

  // Backend-assigned session id (format "<date>-<piece title>"), captured
  // from phrase 1's response and reused for every later phrase in the
  // same recording so they land in one session directory. Null until
  // phrase 1 comes back.
  String? _feedbackSessionId;

  /// Fired by Draggable_Recorder_Button once per phrase, as soon as Rust
  /// finishes analyzing it. Sends it to /api/feedback/phrase, which
  /// judges and returns the phrase's report in the same response, then
  /// reflects the result in the companion's mood.
  ///
  /// TODO — three inputs the real endpoint requires that nothing in this
  /// file currently tracks; wire these in from wherever they actually
  /// live once that's decided:
  ///   - `piece`: title/composer/composed_date for the loaded score —
  ///     probably known back when the piece was picked from the library.
  ///   - `bpm` / `timeSignature`: also piece-level, likely from the same
  ///     place, or from the OMR output below.
  ///   - `expectedNotes`: the ground-truth notes for this phrase's bars —
  ///     presumably the notes_json your OMR pipeline
  ///     (/api/score/process or /api/score/process-omr) already produced
  ///     for this piece, sliced to the bars this phrase covers.
  ///
  /// TODO: once you're happy with the shape, this is also the place to
  /// surface PhraseReport.feedback in the UI (e.g. highlighting the wrong
  /// note on the score via each finding's `box`) rather than only driving
  /// mood.
  Future<void> _onPhraseReceived(int phraseNumber, List<Notes> notes) async {
    final report = await PhraseUploadService.sendPhrase(
      sessionId: _feedbackSessionId,
      phraseNumber: phraseNumber,
      // PLACEHOLDER — see TODO above.
      bpm: 96,
      timeSignature: '4/4',
      piece: const PieceInfo(
        title: 'TODO',
        composer: 'TODO',
        composedDate: 'TODO',
      ),
      expectedNotes: const [],
      userNotes: notes,
    );

    if (report == null || !mounted) return;

    _feedbackSessionId = report.sessionId;

    // ASSUMPTION: overall >= 80 reads as "enjoying", otherwise "mad" —
    // adjust once you have a feel for real score distributions.
    applyPerformanceResult(playedCorrectly: report.scores.overall >= 80);
  }

  // Null until a sheet has been picked from the library.
  Uint8List? _pdfBytes;
  bool get _hasScore => _pdfBytes != null;

  // Owns the fetched-and-parsed pages for whatever score is currently
  // loaded — kept as a stable field (not rebuilt in build()) so it isn't
  // torn down and its cache/prefetch thrown away on every setState.
  ScorePageController? _pageController;

  // Swaps in a new score, or clears it if [pdfBytes] is null.
  void _setScore(Uint8List? pdfBytes) {
    final previousController = _pageController;
    _pdfBytes = pdfBytes;
    _pageController = pdfBytes != null ? ScorePageController(pdfBytes) : null;
    // Close only after the controller's queued renders finish. This prevents
    // a newly selected score from closing a document still used by old pages.
    previousController?.dispose();
  }

  @override
  void dispose() {
    _pageController?.dispose();
    _drawing.dispose();
    super.dispose();
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
  Color _penColor = PracticePalette.gold;
  double _penSize = 3.0;

  void _goToNavPage() async {
    final selected = await Navigator.of(context).push<SelectedSheet>(
      PageRouteBuilder<SelectedSheet>(
        transitionDuration: Motion.page,
        reverseTransitionDuration: Motion.base,
        pageBuilder: (context, animation, secondaryAnimation) =>
            const Music_Library_Page(),
        transitionsBuilder: (context, animation, secondaryAnimation, child) {
          final eased = CurveTween(curve: Motion.enter).animate(animation);
          return SlideTransition(
            position: Tween(
              begin: const Offset(0.0, 1.0),
              end: Offset.zero,
            ).animate(eased),
            child: FadeTransition(opacity: eased, child: child),
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
      key: _scaffoldKey,
      backgroundColor: PracticePalette.ivory,
      drawerEnableOpenDragGesture: false,
      drawer: PracticeSettingsDrawer(
        isRecording: _isRecording,
        feedback: _feedback,
        hasScore: _hasScore,
        onOpenLibrary: () {
          Navigator.pop(context);
          _goToNavPage();
        },
        onClearAnnotations: _drawing.clear,
      ),
      body: SafeArea(
        child: Stack(
          children: [
            // ─────────────────────────────────────────────
            // CLEAN IVORY BACKGROUND
            // ─────────────────────────────────────────────
            const Positioned.fill(
              child: ColoredBox(color: PracticePalette.ivory),
            ),

            // Very subtle top border, matching the reference page.
            Positioned(
              top: 0,
              left: 0,
              right: 0,
              child: Container(
                height: 1,
                color: PracticePalette.lightGold.withValues(alpha: 0.35),
              ),
            ),

            // ─────────────────────────────────────────────
            // SCORE
            // ─────────────────────────────────────────────
            Positioned.fill(
              child: Padding(
                // Keep the score clear of the top tools and bottom actions,
                // while using nearly the entire available width on a phone.
                padding: const EdgeInsets.fromLTRB(
                  Space.sm,
                  72,
                  Space.sm,
                  82,
                ),
                child: Container(
                  decoration: BoxDecoration(
                    color: PracticePalette.paper,
                    borderRadius: Radii.cardRadius,
                    border: Border.all(
                      color: PracticePalette.lightGold.withValues(alpha: 0.65),
                      width: 1,
                    ),
                    boxShadow: Elevations.overlay(PracticePalette.brown),
                  ),
                  clipBehavior: Clip.antiAlias,
                  child: Stack(
                    children: [
                      if (_hasScore)
                        Positioned.fill(
                          child: Score_Pages_View(controller: _pageController!),
                        )
                      else
                        const Center(
                          child: Padding(
                            padding: EdgeInsets.all(Space.xxl),
                            child: Text(
                              'Select a score from the library',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: PracticePalette.mutedBrown,
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
                                _ornamentRule(),
                                const SizedBox(width: Space.sm),
                                Container(
                                  width: 7,
                                  height: 7,
                                  decoration: BoxDecoration(
                                    border: Border.all(
                                      color: PracticePalette.gold.withValues(
                                        alpha: 0.75,
                                      ),
                                    ),
                                    shape: BoxShape.circle,
                                  ),
                                ),
                                const SizedBox(width: Space.sm),
                                _ornamentRule(),
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
                controller: _drawing,
                isDrawingMode: _isDrawingMode,
                isErasing: _isErasing,
                penColor: _penColor,
                penSize: _penSize,
              ),
            ),

            // ─────────────────────────────────────────────
            // SETTINGS
            // ─────────────────────────────────────────────
            Positioned(
              top: 16,
              left: 22,
              child: PracticeToolButton(
                icon: Icons.tune_rounded,
                active: false,
                color: PracticePalette.gold,
                onTap: () => _scaffoldKey.currentState?.openDrawer(),
              ),
            ),

            // ─────────────────────────────────────────────
            // TOP RIGHT DRAWING TOOLS
            // ─────────────────────────────────────────────
            Positioned(
              top: 16,
              right: 22,
              child: Row(
                children: [
                  PracticeToolButton(
                    icon: Icons.edit_outlined,
                    active: _isDrawingMode,
                    color: PracticePalette.gold,
                    onTap: () {
                      setState(() {
                        _isDrawingMode = !_isDrawingMode;
                        if (_isDrawingMode) {
                          _isErasing = false;
                        }
                      });
                    },
                  ),
                  const SizedBox(width: Space.xs),
                  AnimatedBuilder(
                    animation: _drawing,
                    builder: (_, _) => PracticeToolButton(
                      icon: Icons.undo_rounded,
                      active: false,
                      color: PracticePalette.gold,
                      enabled: _drawing.canUndo,
                      onTap: _drawing.undo,
                    ),
                  ),
                  const SizedBox(width: Space.xs),
                  PracticeToolButton(
                    icon: Icons.palette_outlined,
                    active: _showPenSettings,
                    color: PracticePalette.gold,
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
            Positioned(
              top: 68,
              right: 22,
              // Scales and fades out of the palette button rather than
              // appearing outright, so it reads as belonging to the
              // control that opened it.
              child: AnimatedScale(
                scale: _showPenSettings ? 1 : 0.92,
                duration: Motion.fast,
                curve: Motion.enter,
                alignment: Alignment.topRight,
                child: AnimatedOpacity(
                  opacity: _showPenSettings ? 1 : 0,
                  duration: Motion.fast,
                  child: IgnorePointer(
                    ignoring: !_showPenSettings,
                    child: PracticePenPanel(
                      colors: PracticePalette.penColors,
                      selectedColor: _penColor,
                      penSize: _penSize,
                      isErasing: _isErasing,
                      onColorSelected: (color) {
                        setState(() {
                          _penColor = color;
                          _isErasing = false;
                          _isDrawingMode = true;
                        });
                      },
                      onSizeChanged: (size) {
                        setState(() {
                          _penSize = size;
                        });
                      },
                      onEraserToggled: () {
                        setState(() {
                          _isErasing = !_isErasing;
                          if (_isErasing) _isDrawingMode = false;
                        });
                      },
                    ),
                  ),
                ),
              ),
            ),

            // The draggable control owns its own Rust-bridge notesStream()
            // recording pipeline; it reports UI toggle state here and, per
            // phrase, hands the notes off for upload + feedback polling.
            Draggable_Recorder_Button(
              onToggle: _onRecordingChanged,
              onPhrase: _onPhraseReceived,
              accent: PracticeSettingsDrawer.feedbackColor(_feedback),
            ),

            // ─────────────────────────────────────────────
            // SEARCH
            // ─────────────────────────────────────────────
            Positioned(
              left: 22,
              bottom: 20,
              child: PracticeBottomButton(
                icon: Icons.search_rounded,
                color: PracticePalette.mutedBrown,
                onTap: _goToNavPage,
              ),
            ),

            // ─────────────────────────────────────────────
            // EXIT
            // ─────────────────────────────────────────────
            Positioned(
              right: 22,
              bottom: 20,
              child: PracticeBottomButton(
                icon: Icons.arrow_back_rounded,
                color: PracticePalette.mutedBrown,
                onTap: () => Navigator.of(context).maybePop(),
              ),
            ),
          ],
        ),
      ),
    );
  }

  static Widget _ornamentRule() => Container(
    width: 38,
    height: 1,
    color: PracticePalette.lightGold.withValues(alpha: 0.65),
  );
}
