import 'package:flutter/material.dart';

import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// Undo and redo for the Band song, naming the step each one takes.
class SongEditBar extends StatelessWidget {
  const SongEditBar({
    super.key,
    required this.undoLabel,
    required this.redoLabel,
    required this.enabled,
    required this.onUndo,
    required this.onRedo,
  });

  /// What undo takes back ("drums quieter"), or null when there's nothing.
  final String? undoLabel;
  final String? redoLabel;
  final bool enabled;
  final VoidCallback onUndo;
  final VoidCallback onRedo;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Flexible(
          child: TextButton.icon(
            key: const ValueKey('undo'),
            onPressed: enabled && undoLabel != null ? onUndo : null,
            icon: const Icon(Icons.undo_rounded, size: 18),
            label: Text(
              undoLabel == null ? 'Undo' : 'Undo: $undoLabel',
              overflow: TextOverflow.ellipsis,
            ),
            style: TextButton.styleFrom(foregroundColor: PracticePalette.gold),
          ),
        ),
        const SizedBox(width: Space.sm),
        Flexible(
          child: TextButton.icon(
            key: const ValueKey('redo'),
            onPressed: enabled && redoLabel != null ? onRedo : null,
            icon: const Icon(Icons.redo_rounded, size: 18),
            label: Text(
              redoLabel == null ? 'Redo' : 'Redo: $redoLabel',
              overflow: TextOverflow.ellipsis,
            ),
            style: TextButton.styleFrom(foregroundColor: PracticePalette.gold),
          ),
        ),
      ],
    );
  }
}

/// Something the app did on its own, like switching engine, until dismissed.
class EngineNoticeCard extends StatelessWidget {
  const EngineNoticeCard({
    super.key,
    required this.text,
    required this.onDismiss,
  });

  final String text;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const ValueKey('engine-notice'),
      padding: const EdgeInsets.fromLTRB(
        Space.md,
        Space.sm,
        Space.xs,
        Space.sm,
      ),
      decoration: BoxDecoration(
        color: PracticePalette.lightGold.withValues(alpha: 0.3),
        borderRadius: Radii.cardRadius,
        border: Border.all(color: PracticePalette.gold.withValues(alpha: 0.5)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.only(top: 2),
            child: Icon(
              Icons.swap_horiz_rounded,
              size: 18,
              color: PracticePalette.gold,
            ),
          ),
          const SizedBox(width: Space.sm),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(
                color: PracticePalette.brown,
                fontSize: 13,
              ),
            ),
          ),
          IconButton(
            onPressed: onDismiss,
            icon: const Icon(Icons.close_rounded, size: 18),
            color: PracticePalette.mutedBrown,
            tooltip: 'Dismiss',
            visualDensity: VisualDensity.compact,
          ),
        ],
      ),
    );
  }
}
