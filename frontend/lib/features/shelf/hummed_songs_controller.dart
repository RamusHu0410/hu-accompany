import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:hu_accomponist/features/hum/hum_audio.dart';
import 'package:hu_accomponist/integrations/hum/saved_hum_store.dart';

/// The shelf's Hummed tab: the songs saved from the hum page, playing one
/// at a time, renaming and deleting them. The view only draws this.
class HummedSongsController extends ChangeNotifier {
  HummedSongsController({SavedHumStore? store, SongPlayer? player})
    : _store = store ?? FileSavedHumStore(),
      _player = player ?? JustAudioSongPlayer(name: 'shelf') {
    _playingSub = _player.playing.listen((playing) {
      if (playing) {
        _started = true;
      } else if (_started) {
        // only once this song really played: the stop before it starts
        // reports "not playing" too
        _started = false;
        playingId = null;
        _changed();
      }
    });
  }

  final SavedHumStore _store;
  final SongPlayer _player;
  StreamSubscription<bool>? _playingSub;
  bool _disposed = false;
  bool _started = false;

  List<SavedHum> songs = const [];
  bool loading = true;
  String? error;

  /// The song playing now, if any.
  String? playingId;

  Future<void> load() async {
    try {
      songs = await _store.loadAll();
      error = null;
    } on Exception catch (e) {
      error = "Couldn't read your saved songs ($e).";
    }
    loading = false;
    _changed();
  }

  /// Plays [song], or stops it if it's the one playing.
  Future<void> toggle(SavedHum song) async {
    if (playingId == song.id) return stop();
    try {
      final audio = await _store.audioFor(song);
      if (!audio.existsSync()) {
        error = 'That song\'s audio is missing. Delete it and save it again.';
        return _changed();
      }
      await _player.stop();
      _started = false;
      playingId = song.id;
      error = null;
      _changed();
      await _player.playUrl(Uri.file(audio.path));
    } on Exception catch (e) {
      playingId = null;
      error = "Couldn't play that song ($e).";
      _changed();
    }
  }

  Future<void> stop() async {
    playingId = null;
    _changed();
    await _player.stop();
  }

  /// Blank names are ignored.
  Future<void> rename(SavedHum song, String title) async {
    final name = title.trim();
    if (name.isEmpty || name == song.title) return;
    await _store.rename(song.id, name);
    await load();
  }

  Future<void> delete(SavedHum song) async {
    if (playingId == song.id) await stop();
    await _store.delete(song.id);
    await load();
  }

  void _changed() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _playingSub?.cancel();
    _player.dispose();
    super.dispose();
  }
}
