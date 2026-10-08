import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:hu_accomponist/features/hum/hum_chat.dart';
import 'package:hu_accomponist/features/hum/hum_controller.dart';
import 'package:hu_accomponist/features/hum/hum_controls.dart';
import 'package:hu_accomponist/features/hum/hum_notes_view.dart';
import 'package:hu_accomponist/features/hum/hum_record_button.dart';
import 'package:hu_accomponist/features/hum/raw_hum_panel.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// Hum a tune, hear it as a song, and change it with faders or words.
/// All behaviour lives in [HumController]; this only draws it.
class HumPage extends StatefulWidget {
  /// A controller to use instead of making one (tests hand in fakes). The
  /// page disposes only a controller it made itself.
  const HumPage({super.key, this.controller});

  final HumController? controller;

  @override
  State<HumPage> createState() => _HumPageState();
}

class _HumPageState extends State<HumPage> {
  late final HumController _controller = widget.controller ?? HumController();

  @override
  void dispose() {
    if (widget.controller == null) _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.dark,
      child: Scaffold(
        backgroundColor: PracticePalette.ivory,
        body: SafeArea(
          child: ListenableBuilder(
            listenable: _controller,
            builder: (context, _) => Column(
              children: [
                _TopBar(onBack: () => Navigator.of(context).maybePop()),
                Expanded(child: _content()),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _content() {
    final c = _controller;
    return ListView(
      keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
      padding: const EdgeInsets.fromLTRB(
        Space.lg,
        Space.xs,
        Space.lg,
        Space.xxl,
      ),
      children: [
        HumNotesView(notes: c.notes),
        const SizedBox(height: Space.lg),
        Center(
          child: HumRecordButton(
            phase: c.phase,
            onStart: c.startHum,
            onStop: c.stopHum,
          ),
        ),
        if (c.error != null) _ErrorNote(c.error!),
        if (c.hum != null) ...[
          const SizedBox(height: Space.md),
          _SongBar(
            hum: c.hum!,
            isPlaying: c.isPlaying,
            canPlay: c.hasSong && c.phase == HumPhase.idle,
            onToggle: c.togglePlay,
          ),
          const SizedBox(height: Space.md),
          RawHumPanel(playback: c.rawPlayback),
          const SizedBox(height: Space.md),
          HumControls(
            engine: c.engine,
            settings: c.settings,
            onEngine: c.setEngine,
            onFader: c.moveFader,
            onFaderEnd: c.commitSettings,
            onReset: c.resetSettings,
          ),
          const SizedBox(height: Space.md),
          HumChat(messages: c.chat, busy: c.chatBusy, onSend: c.send),
        ],
      ],
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.onBack});

  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(Space.xs, Space.xs, Space.lg, 0),
      child: Row(
        children: [
          IconButton(
            onPressed: onBack,
            icon: const Icon(Icons.arrow_back_rounded),
            color: PracticePalette.mutedBrown,
            tooltip: 'Back',
          ),
          const Text(
            'HUM',
            style: TextStyle(
              color: PracticePalette.brown,
              fontSize: 12,
              fontWeight: FontWeight.w700,
              letterSpacing: 3,
            ),
          ),
        ],
      ),
    );
  }
}

class _ErrorNote extends StatelessWidget {
  const _ErrorNote(this.message);

  final String message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: Space.md),
      child: Text(
        message,
        textAlign: TextAlign.center,
        style: const TextStyle(color: PracticePalette.alert, fontSize: 14),
      ),
    );
  }
}

class _SongBar extends StatelessWidget {
  const _SongBar({
    required this.hum,
    required this.isPlaying,
    required this.canPlay,
    required this.onToggle,
  });

  final HumUpload hum;
  final bool isPlaying;
  final bool canPlay;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final summary = [
      if (hum.key.isNotEmpty) '${hum.key} ${hum.mode}',
      if (hum.tempo > 0) '${hum.tempo.round()} bpm',
      '${hum.noteCount} notes',
    ].join('  ·  ');
    return Row(
      children: [
        IconButton.filled(
          onPressed: canPlay ? onToggle : null,
          icon: Icon(isPlaying ? Icons.stop_rounded : Icons.play_arrow_rounded),
          style: IconButton.styleFrom(
            backgroundColor: PracticePalette.gold,
            foregroundColor: PracticePalette.paper,
          ),
          tooltip: isPlaying ? 'Stop' : 'Play',
        ),
        const SizedBox(width: Space.sm),
        Expanded(
          child: Text(
            summary,
            style: const TextStyle(
              color: PracticePalette.mutedBrown,
              fontSize: 13,
            ),
          ),
        ),
      ],
    );
  }
}
