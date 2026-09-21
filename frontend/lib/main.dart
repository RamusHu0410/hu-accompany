import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';
import 'package:hu_accomponist/features/practice/Draggable_Recorder_Button.dart';
import 'package:hu_accomponist/features/practice/Drawing_Overlay.dart';
import 'package:hu_accomponist/features/search/Music_Library_Page.dart';
import 'package:hu_accomponist/features/practice/Score_Page_Controller.dart';
import 'package:hu_accomponist/features/practice/Score_Pages_View.dart';
import 'dart:typed_data';
import 'package:hu_accomponist/features/home/Vinyl_Loading_Screen.dart';
import 'package:hu_accomponist/features/home/Record_Navigator_Page.dart';
import 'package:hu_accomponist/src/rust/models.dart';
import 'package:hu_accomponist/integrations/feedback/Phrase_send2_server.dart';
import 'package:hu_accomponist/integrations/feedback/Pull_back_phrase.dart';
import 'package:hu_accomponist/features/practice/Phrase_Feedback.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';
import 'package:hu_accomponist/features/practice/Practice_Tool_Buttons.dart';
import 'package:hu_accomponist/features/practice/Practice_Pen_Panel.dart';
import 'package:hu_accomponist/features/practice/Practice_Settings_Drawer.dart';
import 'package:hu_accomponist/features/practice/Practice_Companion.dart';
import 'package:hu_accomponist/integrations/audio/Test_Phrase_Injector.dart';
import 'package:hu_accomponist/integrations/audio/Rust_Bridge.dart';


// Re-exported so anything that already reached for PhraseFeedback through
// main.dart keeps compiling after the enum moved to its own file.
export 'package:hu_accomponist/features/practice/Phrase_Feedback.dart';

// Audio capture is driven through integrations/audio/Audio_Native.dart,
// which owns the dart:ffi lookup of start_recording/stop_recording. Those
// are C symbols rather than flutter_rust_bridge calls because native_ffi
// marks listen_audio/stop_audio as `#[frb(ignore)]`; src/rust/api.dart
// therefore exposes only initSession/getUserData/notesStream.

Future<void> main() async {
  // Attempt to load the native Rust library, but never let a failure here
  // block the UI from rendering.
  // Right now this is expected to potentially fail while the Xcode/cargokit
  // integration for native_ffi is still being fixed; once that's sorted,
  // this try/catch can stay as a permanent safety net regardless.
  // Loading strategy differs per platform (static on iOS, dynamic
  // elsewhere), and failure must never block the UI — see Rust_Bridge.dart.
  await RustBridge.ensureInitialized();

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

  /// The most recent analyzed phrase, handed to the companion for display.
  /// Purely presentational -- [_feedback] still drives the recorder halo,
  /// exactly as before.
  PhraseReport? _latestReport;
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
      setState(() => _latestReport = null);
      setPhraseFeedback(PhraseFeedback.none);
    }
  }

  // Backend-assigned session id (format "<date>-<piece title>"), captured
  // from phrase 1's response and reused for every later phrase in the
  // same recording so they land in one session directory. Null until
  // phrase 1 comes back.
  String? _feedbackSessionId;

  /// Tempo and metre assumed for bar numbering. Nothing in the app knows
  /// the real values for a loaded score; named here so the assumption is
  /// visible rather than sitting as two literals inside the request.
  static const double _assumedBpm = 96;
  static const String _assumedTimeSignature = '4/4';

  /// Overridden only by the debug sample injector, which knows the real
  /// tempo and metre for its fixture.
  double? _sampleBpm;
  String? _sampleTimeSignature;

  /// Ground-truth notes for the loaded piece, in the backend's
  /// expected_notes shape. Empty until something populates it: the OMR
  /// endpoints that would produce it are never called from this app.
  List<Map<String, dynamic>> _expectedNotes = const [];

  /// Fired by Draggable_Recorder_Button once per phrase, as soon as Rust
  /// finishes analyzing it. Sends it to /api/feedback/phrase, which
  /// judges and returns the phrase's report in the same response, then
  /// reflects the result in the companion's mood.
  ///
  /// `piece` now carries the real title and composer captured when the
  /// score was picked from the library (see [_piece]).
  ///
  /// Two inputs still have no source anywhere in the app, and are sent as
  /// documented defaults rather than invented values:
  ///
  ///   - `bpm` / `timeSignature`: nothing tracks the loaded score's tempo
  ///     or metre. /api/score/process takes bpm as an *input*, so it
  ///     cannot supply one either. [_assumedBpm] and [_assumedTimeSignature]
  ///     name that assumption instead of burying two literals in the call;
  ///     the backend uses them only to number bars, so a wrong tempo
  ///     mislabels bar numbers but does not invalidate pitch scoring.
  ///
  ///   - `expectedNotes`: the app never calls /api/score/process or
  ///     /api/score/process-omr, so no OMR note data exists on the device
  ///     for any piece. Sent empty. The backend requires a non-empty
  ///     `expected_notes` to judge against, so until that pipeline is
  ///     called, phrases will come back rejected rather than scored — see
  ///     the diagnostics line below, which says so explicitly in the
  ///     terminal instead of failing silently.
  Future<void> _onPhraseReceived(int phraseNumber, List<Notes> notes) async {
    if (_expectedNotes.isEmpty) {
      debugPrint(
        '[Diagnostics] phrase $phraseNumber: no expected_notes for '
        '"${_piece.title}" — the OMR pipeline (/api/score/process) is never '
        'called by this app, so the backend has nothing to judge against '
        'and will reject this phrase.',
      );
    }

    final report = await PhraseUploadService.sendPhrase(
      sessionId: _feedbackSessionId,
      phraseNumber: phraseNumber,
      bpm: _sampleBpm ?? _assumedBpm,
      timeSignature: _sampleTimeSignature ?? _assumedTimeSignature,
      piece: _piece,
      expectedNotes: _expectedNotes,
      userNotes: notes,
    );

    if (report == null || !mounted) return;

    _feedbackSessionId = report.sessionId;
    // Surfaces the report the call already returns. The request itself is
    // untouched -- this only consumes the response.
    setState(() => _latestReport = report);

    setPhraseFeedback(PhraseFeedback.forScore(report.scores.overall));
  }

  /// Identity of the loaded score, captured when it is picked from the
  /// library and sent with every phrase.
  ///
  /// `composedDate` is empty because nothing in the app knows it: the
  /// library's MusicSheet/WorkSummary carry title, composer and IMSLP url
  /// only. The backend treats `piece` as optional metadata and stores it
  /// as-is, so an empty date is honest; a fabricated one would be written
  /// into every stored phrase file.
  PieceInfo _piece = const PieceInfo(
    title: '',
    composer: '',
    composedDate: '',
  );

  // Null until a sheet has been picked from the library.
  Uint8List? _pdfBytes;
  bool get _hasScore => _pdfBytes != null;

  // Owns the fetched-and-parsed pages for whatever score is currently
  // loaded — kept as a stable field (not rebuilt in build()) so it isn't
  // torn down and its cache/prefetch thrown away on every setState.
  ScorePageController? _pageController;

  // Swaps in a new score, or clears it if [selected] is null.
  void _setScore(SelectedSheet? selected) {
    final pdfBytes = selected?.pdfBytes;
    _piece = selected == null
        ? const PieceInfo(title: '', composer: '', composedDate: '')
        : PieceInfo(
            title: selected.sheet.title,
            composer: selected.composer,
            composedDate: '',
          );
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
    _setScore(widget.selected);
  }

  // Pen settings
  bool _showPenSettings = false;
  Color _penColor = PracticePalette.gold;
  double _penSize = 3.0;

  /// Debug only. Pushes the canned sample phrase through Rust so the full
  /// Rust -> Dart -> Python -> Dart chain can be exercised without working
  /// audio capture. Rust's own status string is surfaced, because the most
  /// common outcome is "no listener" — nothing has subscribed to
  /// notesStream() until recording has been started at least once.
  Future<void> _injectSamplePhrase() async {
    // Stand in for the missing OMR pipeline: without ground truth the
    // backend has nothing to judge against and rejects the phrase, so the
    // fixture's own expected_notes/piece/timing are loaded into the session
    // first. This is exactly the state the app would be in if
    // /api/score/process were ever called for the loaded score.
    final sample = await TestPhraseInjector.loadSample();
    if (sample != null && mounted) {
      setState(() {
        _expectedNotes = sample.expectedNotes;
        _piece = sample.piece;
        _sampleBpm = sample.bpm;
        _sampleTimeSignature = sample.timeSignature;
      });
    }

    final status = await TestPhraseInjector.injectSample();
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(status),
        duration: const Duration(seconds: 3),
      ),
    );
  }

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
        _setScore(selected);
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
            // DEBUG: inject the sample phrase through Rust
            // ─────────────────────────────────────────────
            if (kDebugMode)
              Positioned(
                left: Space.lg,
                bottom: 76,
                child: PracticeBottomButton(
                  icon: Icons.science_outlined,
                  color: PracticePalette.mutedBrown,
                  onTap: _injectSamplePhrase,
                ),
              ),

            // ─────────────────────────────────────────────
            // PHRASE FEEDBACK + COMPANION
            // ─────────────────────────────────────────────
            Positioned(
              right: Space.lg,
              bottom: 76,
              child: PracticeCompanion(
                report: _latestReport,
                isRecording: _isRecording,
              ),
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
