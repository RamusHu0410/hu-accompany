import 'package:flutter/material.dart';
import 'package:hu_accomponist/features/practice/Draggable_Recorder_Button.dart';
import 'package:hu_accomponist/features/practice/Drawing_Overlay.dart';
import 'package:hu_accomponist/features/search/Music_Library_Page.dart';
import 'package:hu_accomponist/features/practice/score_osmd_view.dart';
import 'package:hu_accomponist/integrations/scores/score_models.dart';
import 'package:hu_accomponist/features/home/Vinyl_Loading_Screen.dart';
import 'package:hu_accomponist/features/home/Record_Navigator_Page.dart';
import 'package:hu_accomponist/src/rust/models.dart';
<<<<<<< HEAD
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
=======
import 'package:hu_accomponist/integrations/feedback/Phrase_send2_server.dart';
import 'package:hu_accomponist/integrations/feedback/Pull_back_phrase.dart';
import 'package:hu_accomponist/features/practice/Phrase_Feedback.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';
import 'package:hu_accomponist/features/practice/Practice_Tool_Buttons.dart';
import 'package:hu_accomponist/features/practice/Practice_Pen_Panel.dart';
import 'package:hu_accomponist/features/practice/Practice_Settings_Drawer.dart';
import 'package:hu_accomponist/features/practice/phrase_feedback_overlay.dart';
import 'package:hu_accomponist/features/practice/Exercise_Display.dart';
import 'package:hu_accomponist/features/practice/exercise_picker.dart';
import 'package:hu_accomponist/features/practice/Exercise_Session.dart';
import 'package:hu_accomponist/integrations/audio/Rust_Bridge.dart';
>>>>>>> b60c0a0e4274b32570d119c61e61935cac5cf3ce


// Re-exported so anything that already reached for PhraseFeedback through
// main.dart keeps compiling after the enum moved to its own file.
export 'package:hu_accomponist/features/practice/Phrase_Feedback.dart';

<<<<<<< HEAD

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
=======
// Audio capture is driven through integrations/audio/Audio_Native.dart,
// which owns the dart:ffi lookup of start_recording/stop_recording. Those
// are C symbols rather than flutter_rust_bridge calls because native_ffi
// marks listen_audio/stop_audio as `#[frb(ignore)]`; src/rust/api.dart
// therefore exposes only initSession/getUserData/notesStream.
>>>>>>> b60c0a0e4274b32570d119c61e61935cac5cf3ce

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
  final LoadedScore? selected;
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

  /// The most recent analyzed phrase, handed to the feedback overlay for display.
  /// Purely presentational -- [_feedback] still drives the recorder halo,
  /// exactly as before.
  PhraseReport? _latestReport;

  /// The exercise being practised, if any. While set it replaces the score,
  /// and it is what Rust listens for and the backend judges against.
  ExerciseSession? _exercise;
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
    if (!isRecording) {
      _exercise?.finish();
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

  /// Tempo and metre assumed for bar numbering when the loaded score's
  /// MusicXML does not state them; named here so the assumption is visible
  /// rather than sitting as two literals inside the request.
  static const double _assumedBpm = 96;
  static const String _assumedTimeSignature = '4/4';

  double get _bpm => _score?.summary.tempoBpm ?? _assumedBpm;
  String get _timeSignature {
    final fromScore = _score?.summary.timeSignature ?? '';
    return fromScore.isEmpty ? _assumedTimeSignature : fromScore;
  }

  /// Ground-truth notes for the loaded piece, in the backend's
  /// expected_notes shape. Empty until something populates it: the OMR
  /// endpoints that would produce it are never called from this app.
  List<Map<String, dynamic>> _expectedNotes = const [];

  /// Fired by Draggable_Recorder_Button once per phrase, as soon as Rust
  /// finishes analyzing it. Sends it to /api/feedback/phrase, which
  /// judges and returns the phrase's report in the same response, then
  /// shows the result in the feedback card.
  ///
  /// `piece` now carries the real title and composer captured when the
  /// score was picked from the library (see [_piece]).
  ///
  /// Two inputs still have no source anywhere in the app, and are sent as
  /// documented defaults rather than invented values:
  ///
  ///   - `bpm` / `timeSignature`: taken from the score's MusicXML when it
  ///     states them, otherwise [_assumedBpm] and [_assumedTimeSignature].
  ///     The backend uses them only to number bars, so a wrong tempo
  ///     mislabels bar numbers but does not invalidate pitch scoring.
  ///
  ///   - `expectedNotes`: nothing turns the loaded MusicXML into expected
  ///     notes yet, so it is sent empty. The backend requires a non-empty
  ///     `expected_notes` to judge against, so phrases come back rejected
  ///     rather than scored — see the diagnostics line below, which says
  ///     so explicitly in the terminal instead of failing silently.
  Future<void> _onPhraseReceived(int phraseNumber, List<Notes> notes) async {
    final exercise = _exercise;
    if (exercise != null) {
      exercise.onRustBatch(notes);
      return;
    }

    if (_expectedNotes.isEmpty) {
      debugPrint(
        '[Diagnostics] phrase $phraseNumber: no expected_notes for '
        '"${_piece.title}" — nothing derives expected notes from the '
        'MusicXML yet, so the backend has nothing to judge against and '
        'will reject this phrase.',
      );
    }

    final report = await PhraseUploadService.sendPhrase(
      sessionId: _feedbackSessionId,
      phraseNumber: phraseNumber,
      bpm: _bpm,
      timeSignature: _timeSignature,
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
  /// score catalog carries title and composer only. The backend treats
  /// `piece` as optional metadata and stores it
  /// as-is, so an empty date is honest; a fabricated one would be written
  /// into every stored phrase file.
  PieceInfo _piece = const PieceInfo(
    title: '',
    composer: '',
    composedDate: '',
  );

  // Null until a score has been picked from the library.
  LoadedScore? _score;
  bool get _hasScore => _score != null;

  // Kept as a stable field so picking another score reloads the same
  // WebView instead of rebuilding it.
  final ScoreOsmdController _osmd = ScoreOsmdController();

  // Swaps in a new score, or clears it if [selected] is null.
  void _setScore(LoadedScore? selected) {
    if (selected != null) _endExercise();
    _score = selected;
    _piece = selected == null
        ? const PieceInfo(title: '', composer: '', composedDate: '')
        : PieceInfo(
            title: selected.summary.title,
            composer: selected.summary.composer,
            composedDate: '',
          );
  }

  // ── Exercises ──────────────────────────────────────────────────────

  Future<void> _openExercisePicker() async {
    final choice = await ExercisePicker.show(context);
    if (choice == null || !mounted) return;
    setState(() {
      _endExercise();
      _exercise = ExerciseSession(
        exercise: choice.exercise,
        bpm: choice.bpm,
        octave: choice.octave,
        onReport: _onExerciseReport,
      );
      _latestReport = null;
      _feedback = PhraseFeedback.none;
    });
  }

  void _endExercise() {
    _exercise?.dispose();
    _exercise = null;
  }

  void _onExerciseReport(PhraseReport report) {
    if (!mounted) return;
    setState(() => _latestReport = report);
    setPhraseFeedback(PhraseFeedback.forScore(report.scores.overall));
  }

  /// Runs between the mic tap and the microphone opening. Recording is
  /// refused without an exercise: Rust only listens for the notes of a
  /// loaded piece, and nothing derives those notes from a score's MusicXML
  /// yet, so a score alone gives Rust nothing to listen for.
  Future<bool> _beforeCapture() async {
    final exercise = _exercise;
    if (exercise == null) {
      _say(
        'Pick an exercise first. Following along with a score is not '
        'supported yet.',
      );
      return false;
    }
    final error = await exercise.prepare();
    if (error != null && error != 'cancelled') _say(error);
    return error == null;
  }

  void _say(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), duration: const Duration(seconds: 4)),
    );
  }

  @override
  void dispose() {
    _exercise?.dispose();
    _drawing.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();

    _setScore(widget.selected);
  }

  // Pen settings
  bool _showPenSettings = false;
  Color _penColor = PracticePalette.gold;
  double _penSize = 3.0;

  void _goToNavPage() async {
<<<<<<< HEAD
    final selected = await Navigator.of(context).push<SelectedSheet>(
      PageRouteBuilder<SelectedSheet>(
=======
    final selected = await Navigator.of(context).push<LoadedScore>(
      PageRouteBuilder<LoadedScore>(
>>>>>>> b60c0a0e4274b32570d119c61e61935cac5cf3ce
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
        onOpenExercises: () {
          Navigator.pop(context);
          _openExercisePicker();
        },
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
                      if (_exercise != null)
                        Positioned.fill(
                          child: ExerciseDisplay(session: _exercise!),
                        )
                      else if (_hasScore)
                        Positioned.fill(
                          child: ScoreOsmdView(
                            musicXml: _score!.musicXml,
                            controller: _osmd,
                          ),
                        )
                      else
                        Center(
                          child: Padding(
<<<<<<< HEAD
                            padding: EdgeInsets.all(Space.xxl),
                            child: Text(
                              'Select a score from the library',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: PracticePalette.mutedBrown,
                                fontSize: 15,
                                letterSpacing: 0.4,
                              ),
=======
                            padding: const EdgeInsets.all(Space.xxl),
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const Text(
                                  'Select a score from the library',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                    color: PracticePalette.mutedBrown,
                                    fontSize: 15,
                                    letterSpacing: 0.4,
                                  ),
                                ),
                                const SizedBox(height: Space.md),
                                TextButton.icon(
                                  onPressed: _openExercisePicker,
                                  icon: const Icon(Icons.music_note_rounded),
                                  label: const Text('or practise an exercise'),
                                  style: TextButton.styleFrom(
                                    foregroundColor: PracticePalette.gold,
                                  ),
                                ),
                              ],
>>>>>>> b60c0a0e4274b32570d119c61e61935cac5cf3ce
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
<<<<<<< HEAD
              accent: PracticeSettingsDrawer.feedbackColor(_feedback),
=======
              onBeforeCapture: _beforeCapture,
              onError: _say,
              accent: PracticeSettingsDrawer.feedbackColor(_feedback),
            ),

            // ─────────────────────────────────────────────
            // PHRASE FEEDBACK
            // ─────────────────────────────────────────────
            Positioned(
              right: Space.lg,
              bottom: 76,
              child: PhraseFeedbackOverlay(report: _latestReport),
>>>>>>> b60c0a0e4274b32570d119c61e61935cac5cf3ce
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
