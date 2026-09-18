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




typedef StartRecordingFunc = ffi.Void Function();
typedef StartRecordingFuncDart = void Function();
typedef StopRecordingFunc = ffi.Void Function();
typedef StopRecordingFuncDart = void Function();

/// How the last analyzed phrase went. Drives the recorder's halo tint —
/// [none] while idle or between recordings.
enum PhraseFeedback { none, good, off }

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
        scaffoldBackgroundColor: const Color(0xFFF7F2E7),
        colorScheme: const ColorScheme.light(primary: Color(0xFF9A7A2C)),
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
    const ivory = Color(0xFFF7F2E7);
    const paper = Color(0xFFFFFCF4);
    const brown = Color(0xFF30271F);
    const mutedBrown = Color(0xFF75695B);
    const gold = Color(0xFF9A7A2C);
    const lightGold = Color(0xFFD8C58D);

    return Scaffold(
      key: _scaffoldKey,
      backgroundColor: ivory,
      drawerEnableOpenDragGesture: false,
      drawer: _PracticeSettingsDrawer(
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
            Positioned.fill(child: Container(color: ivory)),

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
                // Keep the score clear of the top tools and bottom actions,
                // while using nearly the entire available width on a phone.
                padding: const EdgeInsets.fromLTRB(12, 72, 12, 82),
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
                          child: Score_Pages_View(controller: _pageController!),
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
              child: _ElegantToolButton(
                icon: Icons.tune_rounded,
                active: false,
                color: gold,
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
                  AnimatedBuilder(
                    animation: _drawing,
                    builder: (_, _) => _ElegantToolButton(
                      icon: Icons.undo_rounded,
                      active: false,
                      color: gold,
                      enabled: _drawing.canUndo,
                      onTap: _drawing.undo,
                    ),
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

            // The draggable control owns its own Rust-bridge notesStream()
            // recording pipeline; it reports UI toggle state here and, per
            // phrase, hands the notes off for upload + feedback polling.
            Draggable_Recorder_Button(
              onToggle: _onRecordingChanged,
              onPhrase: _onPhraseReceived,
              accent: switch (_feedback) {
                PhraseFeedback.good => gold,
                PhraseFeedback.off => const Color(0xFFB2564B),
                PhraseFeedback.none => mutedBrown,
              },
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

class _PracticeSettingsDrawer extends StatelessWidget {
  final bool isRecording;
  final bool hasScore;
  final PhraseFeedback feedback;
  final VoidCallback onOpenLibrary;
  final VoidCallback onClearAnnotations;

  const _PracticeSettingsDrawer({
    required this.isRecording,
    required this.hasScore,
    required this.feedback,
    required this.onOpenLibrary,
    required this.onClearAnnotations,
  });

  @override
  Widget build(BuildContext context) {
    const gold = Color(0xFF9A7A2C);
    const paper = Color(0xFFFFFCF4);
    const brown = Color(0xFF30271F);
    const mutedBrown = Color(0xFF75695B);

    final feedbackLabel = switch (feedback) {
      PhraseFeedback.good => 'Last phrase — on pitch',
      PhraseFeedback.off => 'Last phrase — off pitch',
      PhraseFeedback.none => 'No phrase analyzed yet',
    };

    return Drawer(
      backgroundColor: paper,
      child: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
          children: [
            const Text(
              'SETTINGS',
              style: TextStyle(
                color: gold,
                fontSize: 11,
                letterSpacing: 2.4,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'Practice',
              style: TextStyle(
                color: brown,
                fontSize: 22,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 24),
            _DrawerRow(
              icon: isRecording ? Icons.mic_rounded : Icons.mic_none_rounded,
              iconColor: isRecording ? const Color(0xFFB2564B) : gold,
              label: isRecording ? 'Recording is active' : 'Ready to record',
            ),
            const SizedBox(height: 14),
            _DrawerRow(
              icon: Icons.graphic_eq_rounded,
              iconColor: switch (feedback) {
                PhraseFeedback.good => gold,
                PhraseFeedback.off => const Color(0xFFB2564B),
                PhraseFeedback.none => mutedBrown,
              },
              label: feedbackLabel,
            ),
            const Divider(height: 38),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.library_music_outlined, color: gold),
              title: Text(hasScore ? 'Change score' : 'Open the library'),
              textColor: brown,
              onTap: onOpenLibrary,
            ),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.layers_clear_outlined, color: gold),
              title: const Text('Clear annotations'),
              textColor: brown,
              onTap: onClearAnnotations,
            ),
          ],
        ),
      ),
    );
  }
}

class _DrawerRow extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String label;

  const _DrawerRow({
    required this.icon,
    required this.iconColor,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 18, color: iconColor),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            label,
            style: const TextStyle(color: Color(0xFF30271F), fontSize: 14),
          ),
        ),
      ],
    );
  }
}

class _ElegantToolButton extends StatelessWidget {
  final IconData icon;
  final bool active;
  final bool enabled;
  final Color color;
  final VoidCallback onTap;

  const _ElegantToolButton({
    required this.icon,
    required this.active,
    required this.color,
    required this.onTap,
    this.enabled = true,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: enabled ? onTap : null,
        borderRadius: BorderRadius.circular(30),
        child: AnimatedOpacity(
          duration: const Duration(milliseconds: 180),
          opacity: enabled ? 1 : 0.35,
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
      ),
    );
  }
}

class _ElegantPenPanel extends StatelessWidget {
  final List<Color> colors;
  final Color selectedColor;
  final double penSize;
  final bool isErasing;
  final ValueChanged<Color> onColorSelected;
  final ValueChanged<double> onSizeChanged;
  final VoidCallback onEraserToggled;

  const _ElegantPenPanel({
    required this.colors,
    required this.selectedColor,
    required this.penSize,
    required this.isErasing,
    required this.onColorSelected,
    required this.onSizeChanged,
    required this.onEraserToggled,
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
        border: Border.all(color: lightGold, width: 1),
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
            style: TextStyle(color: gold, fontSize: 10, letterSpacing: 2.5),
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
          Container(height: 1, color: lightGold.withValues(alpha: 0.5)),
          const SizedBox(height: 10),
          Row(
            children: [
              const Icon(Icons.line_weight, size: 15, color: gold),
              Expanded(
                child: SliderTheme(
                  data: SliderTheme.of(context).copyWith(
                    activeTrackColor: gold,
                    inactiveTrackColor: lightGold.withValues(alpha: 0.45),
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
                  style: const TextStyle(color: brown, fontSize: 11),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Container(height: 1, color: lightGold.withValues(alpha: 0.5)),
          const SizedBox(height: 10),
          GestureDetector(
            onTap: onEraserToggled,
            behavior: HitTestBehavior.opaque,
            child: Row(
              children: [
                Icon(
                  Icons.auto_fix_normal_outlined,
                  size: 16,
                  color: isErasing ? gold : brown.withValues(alpha: 0.6),
                ),
                const SizedBox(width: 10),
                Text(
                  'Eraser',
                  style: TextStyle(
                    color: isErasing ? gold : brown,
                    fontSize: 12,
                    fontWeight: isErasing ? FontWeight.w700 : FontWeight.w400,
                  ),
                ),
                const Spacer(),
                AnimatedContainer(
                  duration: const Duration(milliseconds: 160),
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: isErasing ? gold : Colors.transparent,
                    border: Border.all(color: lightGold),
                  ),
                ),
              ],
            ),
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
            border: Border.all(color: const Color(0xFFD8C58D), width: 1),
          ),
          child: Icon(icon, size: 20, color: color),
        ),
      ),
    );
  }
}