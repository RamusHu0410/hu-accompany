import 'package:flutter/material.dart';

import 'package:hu_accomponist/features/hum/chat_controller.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// Change the song by typing or saying what you want. Draws [ChatController]
/// and forwards taps; the controller does the talking.
class HumChat extends StatefulWidget {
  const HumChat({super.key, required this.chat});

  final ChatController chat;

  static const List<String> suggestions = [
    'Softer drums',
    'Make it jazz',
    'Swap the piano for strings',
    'A different chorus',
  ];

  @override
  State<HumChat> createState() => _HumChatState();
}

class _HumChatState extends State<HumChat> {
  final TextEditingController _text = TextEditingController();

  void _send([String? words]) {
    final value = (words ?? _text.text).trim();
    if (value.isEmpty) return;
    widget.chat.send(value);
    _text.clear();
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.chat,
      builder: (context, _) {
        final chat = widget.chat;
        final typing =
            chat.state == ChatVoice.idle || chat.state == ChatVoice.speaking;
        return Container(
          padding: const EdgeInsets.all(Space.md),
          decoration: BoxDecoration(
            color: PracticePalette.paper,
            borderRadius: Radii.cardRadius,
            border: Border.all(
              color: PracticePalette.lightGold.withValues(alpha: 0.65),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  const Expanded(
                    child: Text(
                      'CHANGE IT WITH WORDS',
                      style: TextStyle(
                        color: PracticePalette.gold,
                        fontSize: 11,
                        letterSpacing: 2.4,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  IconButton(
                    key: const ValueKey('speak-replies'),
                    onPressed: chat.toggleSpeakReplies,
                    icon: Icon(
                      chat.speakReplies
                          ? Icons.volume_up_rounded
                          : Icons.volume_off_rounded,
                    ),
                    color: chat.speakReplies
                        ? PracticePalette.gold
                        : PracticePalette.mutedBrown,
                    tooltip: chat.speakReplies
                        ? 'Replies to typing are spoken'
                        : 'Replies to typing are silent',
                    visualDensity: VisualDensity.compact,
                  ),
                ],
              ),
              const Text(
                'Chat edits the Band song. On Epic or Simple, I\'ll switch to Band first.',
                style: TextStyle(
                  color: PracticePalette.mutedBrown,
                  fontSize: 12,
                ),
              ),
              const SizedBox(height: Space.sm),
              if (chat.entries.isEmpty)
                Wrap(
                  spacing: Space.xs,
                  runSpacing: Space.xs,
                  children: [
                    for (final suggestion in HumChat.suggestions)
                      ActionChip(
                        label: Text(suggestion),
                        onPressed: typing ? () => _send(suggestion) : null,
                        backgroundColor: PracticePalette.ivory,
                        side: const BorderSide(
                          color: PracticePalette.lightGold,
                        ),
                        labelStyle: const TextStyle(
                          color: PracticePalette.brown,
                          fontSize: 13,
                        ),
                      ),
                  ],
                )
              else
                for (final entry
                    in chat.entries.reversed.take(8).toList().reversed)
                  _Bubble(entry),
              _VoiceState(chat.state),
              const SizedBox(height: Space.sm),
              Row(
                children: [
                  _MicButton(state: chat.state, onTap: chat.tapMic),
                  const SizedBox(width: Space.xs),
                  Expanded(
                    child: TextField(
                      controller: _text,
                      enabled: typing,
                      textInputAction: TextInputAction.send,
                      onSubmitted: _send,
                      decoration: InputDecoration(
                        hintText: 'e.g. softer drums, make it jazz',
                        isDense: true,
                        filled: true,
                        fillColor: PracticePalette.ivory,
                        border: OutlineInputBorder(
                          borderRadius: Radii.pillRadius,
                          borderSide: BorderSide.none,
                        ),
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: Space.md,
                          vertical: Space.sm,
                        ),
                      ),
                    ),
                  ),
                  IconButton(
                    onPressed: typing ? _send : null,
                    icon: const Icon(Icons.arrow_upward_rounded),
                    color: PracticePalette.gold,
                    tooltip: 'Send',
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}

class _MicButton extends StatelessWidget {
  const _MicButton({required this.state, required this.onTap});

  final ChatVoice state;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final listening = state == ChatVoice.listening;
    return IconButton.filled(
      key: const ValueKey('chat-mic'),
      onPressed: state == ChatVoice.thinking ? null : onTap,
      icon: Icon(listening ? Icons.stop_rounded : Icons.mic_rounded),
      style: IconButton.styleFrom(
        backgroundColor: listening
            ? PracticePalette.alert
            : PracticePalette.gold,
        foregroundColor: PracticePalette.paper,
      ),
      tooltip: switch (state) {
        ChatVoice.listening => 'Stop and send',
        ChatVoice.speaking => 'Interrupt and speak',
        _ => 'Say it',
      },
    );
  }
}

class _VoiceState extends StatelessWidget {
  const _VoiceState(this.state);

  final ChatVoice state;

  @override
  Widget build(BuildContext context) {
    final text = switch (state) {
      ChatVoice.idle => null,
      ChatVoice.listening =>
        'Listening... tap the stop button when you\'re done.',
      ChatVoice.thinking => 'Thinking...',
      ChatVoice.speaking => 'Speaking... tap the mic to interrupt.',
    };
    if (text == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: Space.xs),
      child: Row(
        children: [
          if (state == ChatVoice.thinking)
            const SizedBox(
              width: 12,
              height: 12,
              child: CircularProgressIndicator(
                strokeWidth: 1.5,
                color: PracticePalette.gold,
              ),
            )
          else
            Icon(
              state == ChatVoice.listening
                  ? Icons.hearing_rounded
                  : Icons.record_voice_over_rounded,
              size: 14,
              color: PracticePalette.gold,
            ),
          const SizedBox(width: Space.xs),
          Text(
            text,
            style: const TextStyle(
              color: PracticePalette.mutedBrown,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble(this.entry);

  final ChatEntry entry;

  @override
  Widget build(BuildContext context) {
    if (entry.speaker == ChatSpeaker.notice) {
      return Container(
        margin: const EdgeInsets.only(bottom: Space.xs),
        padding: const EdgeInsets.all(Space.sm),
        decoration: BoxDecoration(
          color: PracticePalette.lightGold.withValues(alpha: 0.25),
          borderRadius: Radii.cardRadius,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(
              Icons.info_outline_rounded,
              size: 16,
              color: PracticePalette.gold,
            ),
            const SizedBox(width: Space.xs),
            Expanded(
              child: Text(
                entry.text,
                style: const TextStyle(
                  color: PracticePalette.brown,
                  fontSize: 13,
                ),
              ),
            ),
          ],
        ),
      );
    }
    final mine = entry.speaker == ChatSpeaker.user;
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: Space.xs),
        padding: const EdgeInsets.symmetric(
          horizontal: Space.sm,
          vertical: Space.xs,
        ),
        constraints: const BoxConstraints(maxWidth: 280),
        decoration: BoxDecoration(
          color: mine
              ? PracticePalette.gold.withValues(alpha: 0.16)
              : PracticePalette.ivory,
          borderRadius: Radii.cardRadius,
        ),
        child: Text(
          entry.text,
          style: const TextStyle(color: PracticePalette.brown, fontSize: 14),
        ),
      ),
    );
  }
}
