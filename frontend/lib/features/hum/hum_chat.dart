import 'package:flutter/material.dart';

import 'package:hu_accomponist/features/hum/hum_controller.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// Change the song by saying what you want in words. Replies are the
/// backend's: it works out what was asked and edits the song's settings.
class HumChat extends StatefulWidget {
  const HumChat({
    super.key,
    required this.messages,
    required this.busy,
    required this.onSend,
  });

  final List<ChatMessage> messages;
  final bool busy;
  final ValueChanged<String> onSend;

  static const List<String> suggestions = [
    'Make it faster',
    'Add a violin',
    'More emotional',
  ];

  @override
  State<HumChat> createState() => _HumChatState();
}

class _HumChatState extends State<HumChat> {
  final TextEditingController _text = TextEditingController();

  void _send([String? words]) {
    final value = (words ?? _text.text).trim();
    if (value.isEmpty || widget.busy) return;
    widget.onSend(value);
    _text.clear();
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
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
          const Text(
            'CHANGE IT WITH WORDS',
            style: TextStyle(
              color: PracticePalette.gold,
              fontSize: 11,
              letterSpacing: 2.4,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: Space.sm),
          if (widget.messages.isEmpty)
            Wrap(
              spacing: Space.xs,
              children: [
                for (final suggestion in HumChat.suggestions)
                  ActionChip(
                    label: Text(suggestion),
                    onPressed: widget.busy ? null : () => _send(suggestion),
                    backgroundColor: PracticePalette.ivory,
                    side: const BorderSide(color: PracticePalette.lightGold),
                    labelStyle: const TextStyle(
                      color: PracticePalette.brown,
                      fontSize: 13,
                    ),
                  ),
              ],
            )
          else
            for (final message
                in widget.messages.reversed.take(6).toList().reversed)
              _Bubble(message),
          if (widget.busy)
            const Padding(
              padding: EdgeInsets.only(top: Space.xs),
              child: Text(
                'Thinking...',
                style: TextStyle(
                  color: PracticePalette.mutedBrown,
                  fontSize: 12,
                ),
              ),
            ),
          const SizedBox(height: Space.sm),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _text,
                  enabled: !widget.busy,
                  textInputAction: TextInputAction.send,
                  onSubmitted: _send,
                  decoration: InputDecoration(
                    hintText: 'e.g. make it sadder',
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
                onPressed: widget.busy ? null : _send,
                icon: const Icon(Icons.arrow_upward_rounded),
                color: PracticePalette.gold,
                tooltip: 'Send',
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble(this.message);

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final mine = message.fromUser;
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
          message.text,
          style: const TextStyle(color: PracticePalette.brown, fontSize: 14),
        ),
      ),
    );
  }
}
