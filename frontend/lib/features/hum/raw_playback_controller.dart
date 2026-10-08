import 'dart:async';
import 'dart:ui';

import 'package:flutter/foundation.dart';

import 'package:hu_accomponist/features/hum/file_sharer.dart';
import 'package:hu_accomponist/features/hum/hum_audio.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/integrations/hum/hum_repository.dart';
import 'package:hu_accomponist/integrations/server/api_client.dart';

/// "Play back my hum": the notes exactly as hummed (no quantizing, no
/// arrangement) on a piano or a plain synth, which notes are sounding as it
/// plays, and the notes as a MIDI file to share.
///
/// Has no UI of its own; the piano roll and its buttons only read this.
class RawPlaybackController extends ChangeNotifier {
  RawPlaybackController({
    required HumRepository repository,
    required SongPlayer player,
    FileSharer sharer = const SystemFileSharer(),
    this.beforePlay,
  }) : _repository = repository,
       _player = player,
       _sharer = sharer {
    _subscriptions = [
      _player.playing.listen(_onPlaying),
      _player.position.listen(_onPosition),
    ];
  }

  final HumRepository _repository;
  final SongPlayer _player;
  final FileSharer _sharer;

  /// Runs before the hum starts, so something else playing can stop first.
  final Future<void> Function()? beforePlay;

  RawHum? hum;
  RawInstrument instrument = RawInstrument.piano;
  bool loading = false;
  bool fetchingAudio = false;
  bool exporting = false;
  bool isPlaying = false;
  String? error;

  /// Seconds into the hum, while it plays.
  double position = 0;

  HumUpload? _upload;
  final Map<RawInstrument, Uint8List> _audio = {};
  late final List<StreamSubscription<Object>> _subscriptions;
  bool _disposed = false;

  /// The notes sounding right now, by index into `hum.notes`.
  Set<int> get sounding =>
      isPlaying && hum != null ? hum!.soundingAt(position) : const {};

  bool get canPlay => hum != null && !loading;

  /// Fetches the raw notes of a newly uploaded hum.
  Future<void> load(HumUpload upload) async {
    await stop();
    _upload = upload;
    _audio.clear();
    hum = null;
    error = null;
    loading = true;
    _changed();
    try {
      final notes = await _repository.raw(upload);
      if (!identical(upload, _upload)) return; // a newer hum arrived meanwhile
      hum = notes;
    } on ApiException catch (e) {
      if (identical(upload, _upload)) error = e.message;
    } on Exception catch (e) {
      if (identical(upload, _upload)) error = "Couldn't read your hum ($e).";
    } finally {
      if (identical(upload, _upload)) {
        loading = false;
        _changed();
      }
    }
  }

  Future<void> setInstrument(RawInstrument next) async {
    if (next == instrument) return;
    instrument = next;
    _changed();
    if (isPlaying) await play(); // carry on, on the new sound
  }

  Future<void> togglePlay() => isPlaying ? stop() : play();

  Future<void> play() async {
    final upload = _upload;
    if (upload == null || !canPlay) return;
    error = null;
    try {
      var audio = _audio[instrument];
      if (audio == null) {
        fetchingAudio = true;
        _changed();
        audio = await _repository.rawAudio(upload, instrument);
        if (!identical(upload, _upload)) return;
        _audio[instrument] = audio;
      }
      await beforePlay?.call();
      position = 0;
      await _player.playWav(audio);
    } on ApiException catch (e) {
      error = e.message;
    } on Exception catch (e) {
      error = "Couldn't play your hum ($e).";
    } finally {
      fetchingAudio = false;
      _changed();
    }
  }

  Future<void> stop() async {
    if (isPlaying) await _player.stop();
  }

  /// Shares the raw notes as hum.mid. [origin] anchors the share sheet on iPad.
  Future<void> exportMidi({Rect? origin}) async {
    final upload = _upload;
    if (upload == null || exporting) return;
    exporting = true;
    error = null;
    _changed();
    try {
      final midi = await _repository.rawMidi(upload);
      await _sharer.share(
        midi,
        filename: 'hum.mid',
        mimeType: 'audio/midi',
        origin: origin,
      );
    } on ApiException catch (e) {
      error = e.message;
    } on Exception catch (e) {
      error = "Couldn't export the MIDI file ($e).";
    } finally {
      exporting = false;
      _changed();
    }
  }

  void _onPlaying(bool playing) {
    if (playing == isPlaying) return;
    isPlaying = playing;
    if (!playing) position = 0;
    _changed();
  }

  void _onPosition(Duration at) {
    if (!isPlaying) return;
    // Ticks every 30 to 60 ms: the playhead moves and notes light up as they start.
    position = at.inMicroseconds / 1e6;
    _changed();
  }

  void _changed() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    for (final subscription in _subscriptions) {
      subscription.cancel();
    }
    _player.dispose();
    super.dispose();
  }
}
