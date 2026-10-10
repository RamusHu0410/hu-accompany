import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

/// Points at one specific note inside the score — zero-based measure,
/// voice-entry, and note-within-that-voice-entry index, in the same order
/// the notes appear in the source MusicXML. This is how "this note was
/// played wrong" gets mapped onto the rendered engraving.
class NoteRef {
  final int measure;
  final int voiceEntry;
  final int noteIndex;
  const NoteRef({
    required this.measure,
    required this.voiceEntry,
    required this.noteIndex,
  });

  Map<String, int> toJson() => {
    'measure': measure,
    'voiceEntry': voiceEntry,
    'noteIndex': noteIndex,
  };
}

/// What a touch on the score does. With [InkMode.pen] or [InkMode.eraser],
/// one finger draws or erases and two fingers scroll and zoom; with
/// [InkMode.off], one finger scrolls. Pinching zooms in every mode.
enum InkMode { off, pen, eraser }

/// Drives the OSMD WebView: loads MusicXML, colors or resets individual
/// notes, and holds the pen ink drawn on the score (inside the page, so it
/// scrolls and zooms with the music), without re-fetching or re-navigating
/// anything. Calls made before
/// the page's JS bridge (`window.OSMDBridge`) has announced itself ready
/// are queued and flushed once the 'bridgeReady' message arrives — NOT
/// just once WebView's onPageFinished fires, since the OSMD script may
/// still be executing at that point.
class ScoreOsmdController {
  WebViewController? _web;
  bool _bridgeReady = false;
  final List<String> _pendingCalls = [];

  /// Whether there's ink to undo on the score.
  final ValueNotifier<bool> canUndoInk = ValueNotifier(false);

  /// Called with the score's strokes (JSON) whenever the ink changes, so
  /// they can be kept for next time.
  void Function(String strokesJson)? onInkChanged;

  /// The ink the next loaded score starts with (see [setInk]).
  String _inkJson = '[]';

  /// A freshly attached WebView has not loaded the bridge yet, so calls
  /// queue until its own 'bridgeReady' arrives.
  void attach(WebViewController controller) {
    _web = controller;
    _bridgeReady = false;
  }

  void onBridgeReady() {
    _bridgeReady = true;
    for (final call in _pendingCalls) {
      _web?.runJavaScript(call);
    }
    _pendingCalls.clear();
  }

  /// Call this if the page navigates again (e.g. a hot restart of the
  /// WebView) so pending calls queue up again instead of firing into a
  /// bridge that no longer exists.
  void reset() {
    _bridgeReady = false;
  }

  void _call(String js) {
    if (_bridgeReady && _web != null) {
      _web!.runJavaScript(js);
    } else {
      _pendingCalls.add(js);
    }
  }

  Future<void> loadScore(String musicXml) async {
    final encoded = jsonEncode(musicXml);
    canUndoInk.value = false;
    _call('OSMDBridge.loadScore($encoded); OSMDBridge.setInk($_inkJson);');
  }

  /// The strokes to show on the score (JSON, as [onInkChanged] gave them).
  /// Set it before or after the score loads; a new score should start with
  /// '[]' until its own ink is known.
  void setInk(String strokesJson) {
    _inkJson = strokesJson;
    canUndoInk.value = false;
    _call('OSMDBridge.setInk($strokesJson);');
  }

  void setInkMode(InkMode mode, {Color? color, double? width}) {
    final hex = color == null ? 'null' : '"${_hex(color)}"';
    _call('OSMDBridge.setInkMode("${mode.name}", $hex, ${width ?? 'null'});');
  }

  void undoInk() => _call('OSMDBridge.undoInk();');

  void clearInk() => _call('OSMDBridge.clearInk();');

  void _inkMessage(Map<String, dynamic>? payload) {
    if (payload == null) return;
    canUndoInk.value = payload['canUndo'] == true;
    _inkJson = jsonEncode(payload['strokes'] ?? const []);
    onInkChanged?.call(_inkJson);
  }

  static String _hex(Color color) =>
      '#${color.toARGB32().toRadixString(16).padLeft(8, '0').substring(2)}';

  /// Colors the given notes (e.g. ones flagged as wrong by your audio
  /// analysis) — defaults to red. Call [resetColors] to clear all of them.
  Future<void> colorNotes(
    List<NoteRef> notes, {
    Color color = const Color(0xFFE53935),
  }) async {
    if (notes.isEmpty) return;
    final hex = _hex(color);
    final refsJson = jsonEncode(notes.map((n) => n.toJson()).toList());
    _call('OSMDBridge.colorNotes($refsJson, "$hex");');
  }

  Future<void> resetColors() async {
    _call('OSMDBridge.resetColors();');
  }
}

/// Renders MusicXML with OpenSheetMusicDisplay inside a WebView. OSMD owns
/// its own layout and scrolling, so this is one continuous view rather than
/// discrete pages. OSMD is bundled under assets/osmd/, so it works offline.
class ScoreOsmdView extends StatefulWidget {
  final String musicXml;
  final ScoreOsmdController controller;

  const ScoreOsmdView({
    super.key,
    required this.musicXml,
    required this.controller,
  });

  @override
  State<ScoreOsmdView> createState() => _ScoreOsmdViewState();
}

class _ScoreOsmdViewState extends State<ScoreOsmdView> {
  late final WebViewController _web;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    widget.controller.attach(_buildWebViewController());
  }

  WebViewController _buildWebViewController() {
    _web = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0x00000000))
      ..addJavaScriptChannel(
        'FlutterBridge',
        onMessageReceived: _onBridgeMessage,
      )
      ..setNavigationDelegate(
        NavigationDelegate(
          // NOTE: we deliberately do NOT call loadScore() here. This only
          // tells us the HTML document finished parsing — the OSMD script
          // (and window.OSMDBridge) may still be executing. The
          // actual "safe to call JS" signal is the 'bridgeReady' message
          // posted from the page itself once OSMDBridge exists.
          onWebResourceError: (error) {
            if (mounted) {
              setState(() {
                _loading = false;
                _error = 'Failed to load score viewer: ${error.description}';
              });
            }
          },
        ),
      )
      // Case-sensitive on iOS. The page loads opensheetmusicdisplay.min.js
      // from the same asset folder.
      ..loadFlutterAsset('assets/osmd/osmd_viewer.html');
    return _web;
  }

  @override
  void didUpdateWidget(covariant ScoreOsmdView oldWidget) {
    super.didUpdateWidget(oldWidget);
    // A new sheet was selected — reload it into the same WebView instead
    // of tearing down and recreating the page.
    if (widget.musicXml != oldWidget.musicXml) {
      setState(() {
        _loading = true;
        _error = null;
      });
      widget.controller.loadScore(widget.musicXml);
    }
  }

  void _onBridgeMessage(JavaScriptMessage message) {
    final data = jsonDecode(message.message) as Map<String, dynamic>;
    switch (data['type']) {
      case 'bridgeReady':
        // window.OSMDBridge now exists — safe to flush queued calls and
        // kick off the very first loadScore.
        widget.controller.onBridgeReady();
        widget.controller.loadScore(widget.musicXml);
        break;
      case 'loaded':
        if (mounted) setState(() => _loading = false);
        break;
      case 'ink':
        widget.controller._inkMessage(data['payload'] as Map<String, dynamic>?);
        break;
      case 'error':
        if (mounted) {
          setState(() {
            _loading = false;
            _error = data['payload']?['message']?.toString();
          });
        }
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        WebViewWidget(controller: _web),
        if (_loading)
          const Center(child: CircularProgressIndicator(strokeWidth: 2.5)),
        if (_error != null)
          Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Text(
                "Couldn't render score: $_error",
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.black.withValues(alpha: 0.5)),
              ),
            ),
          ),
      ],
    );
  }
}
