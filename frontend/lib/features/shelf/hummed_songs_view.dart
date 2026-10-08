import 'package:flutter/material.dart';

import 'package:hu_accomponist/features/shelf/hummed_song_row.dart';
import 'package:hu_accomponist/features/shelf/hummed_songs_controller.dart';
import 'package:hu_accomponist/integrations/hum/saved_hum_store.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// The shelf's Hummed tab: one row per saved song, tap to play. Everything
/// it does goes through [HummedSongsController].
class HummedSongsView extends StatelessWidget {
  const HummedSongsView({
    super.key,
    required this.controller,
    required this.brightness,
  });

  final HummedSongsController controller;
  final Brightness brightness;

  @override
  Widget build(BuildContext context) {
    final text = ShelfPalette.textColor(brightness);
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final c = controller;
        if (c.loading) return const Center(child: CircularProgressIndicator());
        if (c.songs.isEmpty) return _Empty(textColor: text, error: c.error);
        return ListView(
          physics: AppScroll.physics,
          padding: const EdgeInsets.fromLTRB(
            Space.lg,
            Space.md,
            Space.lg,
            Space.xxl,
          ),
          children: [
            if (c.error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: Space.sm),
                child: Text(
                  c.error!,
                  style: const TextStyle(color: PracticePalette.alert),
                ),
              ),
            for (final song in c.songs)
              HummedSongRow(
                key: ValueKey('hummed-${song.id}'),
                song: song,
                playing: c.playingId == song.id,
                brightness: brightness,
                onTap: () => c.toggle(song),
                onRename: () => _rename(context, song),
                onDelete: () => _delete(context, song),
              ),
          ],
        );
      },
    );
  }

  Future<void> _rename(BuildContext context, SavedHum song) async {
    final field = TextEditingController(text: song.title);
    final name = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Rename'),
        content: TextField(
          controller: field,
          autofocus: true,
          maxLength: 60,
          onSubmitted: (value) => Navigator.pop(context, value),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, field.text),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    field.dispose();
    if (name != null) await controller.rename(song, name);
  }

  Future<void> _delete(BuildContext context, SavedHum song) async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this song?'),
        content: Text('"${song.title}" will be gone from this device.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Keep'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (sure ?? false) await controller.delete(song);
  }
}

class _Empty extends StatelessWidget {
  const _Empty({required this.textColor, this.error});

  final Color textColor;
  final String? error;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.xxxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.graphic_eq_rounded,
              size: 40,
              color: textColor.withValues(alpha: 0.3),
            ),
            const SizedBox(height: Space.md),
            Text(
              'No hummed songs yet',
              style: TextStyle(
                color: textColor.withValues(alpha: 0.85),
                fontSize: 16,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: Space.xs),
            Text(
              error ?? 'Hum a tune, tap Save, and it will\nbe kept here.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: textColor.withValues(alpha: 0.5),
                fontSize: 13,
                height: 1.45,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
