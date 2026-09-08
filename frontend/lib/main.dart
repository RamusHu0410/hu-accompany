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

/// Which companion is shown beside the score.
enum CharacterType { wave, tsundereMusic }

/// The three visual reactions available for Tsundere Music.
///
/// The Rust performance callback should set this to [mad] for a wrong note,
/// [enjoying] for a correct note, and [normal] while idle or between phrases.
enum CharacterMood { normal, mad, enjoying }

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

  CharacterType _selectedCharacter = CharacterType.wave;
  CharacterMood _tsundereMood = CharacterMood.normal;

  String get _characterAsset {
    switch (_selectedCharacter) {
      case CharacterType.wave:
        return 'assets/images/wave.png';
      case CharacterType.tsundereMusic:
        switch (_tsundereMood) {
          case CharacterMood.normal:
            return 'assets/images/Tsundere_Music.png';
          case CharacterMood.mad:
            return 'assets/images/Tsundere_Music_Mad.png';
          case CharacterMood.enjoying:
            return 'assets/images/Tsundere_Music_Listen.png';
        }
    }
  }

  /// Call this from the Flutter-Rust-Bridge performance-result callback.
  void setCharacterMood(CharacterMood mood) {
    if (!mounted) return;
    setState(() => _tsundereMood = mood);
  }

  /// Convenience entry point for a Rust result that reports whether a note
  /// was correct. Replace the bool with the Rust result type when it is wired
  /// into Flutter-Rust-Bridge.
  void applyPerformanceResult({required bool playedCorrectly}) {
    setCharacterMood(
      playedCorrectly ? CharacterMood.enjoying : CharacterMood.mad,
    );
  }

  void _onRecordingChanged(bool isRecording) {
    if (isRecording) {
      _nativeBridge.startRecording();
    } else {
      _nativeBridge.stopRecording();
      // The next Rust analysis result will replace this idle expression.
      setCharacterMood(CharacterMood.normal);
    }

    if (mounted) {
      setState(() => _isRecording = isRecording);
    }
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
    _pdfBytes = pdfBytes;
    _pageController = pdfBytes != null ? ScorePageController(pdfBytes) : null;
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
      drawer: _CharacterSettingsDrawer(
        selectedCharacter: _selectedCharacter,
        selectedMood: _tsundereMood,
        isRecording: _isRecording,
        onCharacterChanged: (character) {
          setState(() => _selectedCharacter = character);
        },
        onMoodChanged: setCharacterMood,
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
            // CHARACTER COMPANION
            // ─────────────────────────────────────────────
            Positioned(
              right: 0,
              bottom: 0,
              child: IgnorePointer(
                child: SizedBox(
                  // Tsundere is intentionally smaller than Wave so the score
                  // remains easy to read. Both images are bottom-right aligned
                  // so their feet sit on the screen's bottom edge.
                  width: _selectedCharacter == CharacterType.tsundereMusic
                      ? 205
                      : 250,
                  height: _selectedCharacter == CharacterType.tsundereMusic
                      ? 285
                      : 310,
                  child: AnimatedSwitcher(
                    duration: const Duration(milliseconds: 220),
                    child: Image.asset(
                      _characterAsset,
                      key: ValueKey(_characterAsset),
                      fit: BoxFit.contain,
                      alignment: Alignment.bottomRight,
                    ),
                  ),
                ),
              ),
            ),

            // The draggable control already uses LiquidGlassLens. Its toggle
            // calls the Rust-backed C bridge above.
            Draggable_Recorder_Button(onToggle: _onRecordingChanged),

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

class _CharacterSettingsDrawer extends StatelessWidget {
  final CharacterType selectedCharacter;
  final CharacterMood selectedMood;
  final bool isRecording;
  final ValueChanged<CharacterType> onCharacterChanged;
  final ValueChanged<CharacterMood> onMoodChanged;

  const _CharacterSettingsDrawer({
    required this.selectedCharacter,
    required this.selectedMood,
    required this.isRecording,
    required this.onCharacterChanged,
    required this.onMoodChanged,
  });

  @override
  Widget build(BuildContext context) {
    const gold = Color(0xFF9A7A2C);
    const paper = Color(0xFFFFFCF4);
    const brown = Color(0xFF30271F);

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
              'Your practice companion',
              style: TextStyle(
                color: brown,
                fontSize: 22,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 20),
            RadioListTile<CharacterType>(
              contentPadding: EdgeInsets.zero,
              title: const Text('Wave character'),
              value: CharacterType.wave,
              groupValue: selectedCharacter,
              activeColor: gold,
              onChanged: (value) {
                if (value != null) onCharacterChanged(value);
              },
            ),
            RadioListTile<CharacterType>(
              contentPadding: EdgeInsets.zero,
              title: const Text('Tsundere Music'),
              value: CharacterType.tsundereMusic,
              groupValue: selectedCharacter,
              activeColor: gold,
              onChanged: (value) {
                if (value != null) onCharacterChanged(value);
              },
            ),
            const Divider(height: 38),
            const Text(
              'TSUNDERE EXPRESSION',
              style: TextStyle(
                color: gold,
                fontSize: 11,
                letterSpacing: 1.6,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                ChoiceChip(
                  label: const Text('Normal'),
                  selected: selectedMood == CharacterMood.normal,
                  selectedColor: gold.withValues(alpha: 0.22),
                  onSelected: (_) => onMoodChanged(CharacterMood.normal),
                ),
                ChoiceChip(
                  label: const Text('Mad'),
                  selected: selectedMood == CharacterMood.mad,
                  selectedColor: gold.withValues(alpha: 0.22),
                  onSelected: (_) => onMoodChanged(CharacterMood.mad),
                ),
                ChoiceChip(
                  label: const Text('Enjoying'),
                  selected: selectedMood == CharacterMood.enjoying,
                  selectedColor: gold.withValues(alpha: 0.22),
                  onSelected: (_) => onMoodChanged(CharacterMood.enjoying),
                ),
              ],
            ),
            const SizedBox(height: 30),
            Row(
              children: [
                Icon(
                  isRecording ? Icons.mic_rounded : Icons.mic_none_rounded,
                  size: 18,
                  color: isRecording ? Colors.redAccent : gold,
                ),
                const SizedBox(width: 8),
                Text(
                  isRecording ? 'Recording is active' : 'Ready to record',
                  style: const TextStyle(color: brown),
                ),
              ],
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
