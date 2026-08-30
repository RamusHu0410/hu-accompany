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

/// Drives the OSMD WebView: loads MusicXML, and colors or resets individual
/// notes without re-fetching or re-navigating anything. Calls made before
/// the page's JS bridge (`window.OSMDBridge`) has announced itself ready
/// are queued and flushed once the 'bridgeReady' message arrives — NOT
/// just once WebView's onPageFinished fires, since the CDN-hosted OSMD
/// script may still be loading/executing at that point.
class ScoreOsmdController {
  WebViewController? _web;
  bool _bridgeReady = false;
  final List<String> _pendingCalls = [];

  void attach(WebViewController controller) => _web = controller;

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
    _call('OSMDBridge.loadScore($encoded);');
  }

  /// Colors the given notes (e.g. ones flagged as wrong by your audio
  /// analysis) — defaults to red. Call [resetColors] to clear all of them.
  Future<void> colorNotes(
    List<NoteRef> notes, {
    Color color = const Color(0xFFE53935),
  }) async {
    if (notes.isEmpty) return;
    final hex =
        '#${color.toARGB32().toRadixString(16).padLeft(8, '0').substring(2)}';
    final refsJson = jsonEncode(notes.map((n) => n.toJson()).toList());
    _call('OSMDBridge.colorNotes($refsJson, "$hex");');
  }

  Future<void> resetColors() async {
    _call('OSMDBridge.resetColors();');
  }
}

/// Renders a score by loading OpenSheetMusicDisplay inside a WebView. OSMD
/// owns its own internal layout/scrolling — this is a single continuous
/// view rather than the old discrete-page setup, since real engraving
/// doesn't paginate the same way the placeholder did.
class Score_Osmd_View extends StatefulWidget {
  final String musicXml;
  final ScoreOsmdController controller;

  const Score_Osmd_View({
    super.key,
    required this.musicXml,
    required this.controller,
  });

  @override
  State<Score_Osmd_View> createState() => _Score_Osmd_ViewState();
}

class _Score_Osmd_ViewState extends State<Score_Osmd_View> {
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
          // tells us the HTML document finished parsing — the CDN-hosted
          // OSMD script (and window.OSMDBridge) may still be loading. The
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
      // Asset path must exactly match the file under your assets/ folder
      // (and its pubspec.yaml entry) — case-sensitive on iOS/Linux builds.
      ..loadFlutterAsset('assets/osmd_viewer.html');
    return _web;
  }

  @override
  void didUpdateWidget(covariant Score_Osmd_View oldWidget) {
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
