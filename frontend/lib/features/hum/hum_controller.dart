import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:hu_accomponist/features/hum/band_session.dart';
import 'package:hu_accomponist/features/hum/chat_controller.dart';
import 'package:hu_accomponist/features/hum/engine_guide.dart';
import 'package:hu_accomponist/features/hum/file_sharer.dart';
import 'package:hu_accomponist/features/hum/hum_audio.dart';
import 'package:hu_accomponist/features/hum/raw_playback_controller.dart';
import 'package:hu_accomponist/features/hum/song_saving.dart';
import 'package:hu_accomponist/integrations/hum/chat_models.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/integrations/hum/hum_repository.dart';
import 'package:hu_accomponist/integrations/hum/saved_hum_store.dart';
import 'package:hu_accomponist/integrations/hum/song_project.dart';
import 'package:hu_accomponist/integrations/hum/song_style.dart';
import 'package:hu_accomponist/integrations/server/api_client.dart';

part 'hum_band_editing.dart';
part 'hum_saving.dart';

/// What the hum page is busy with.
enum HumPhase {
  idle,
  recording,

  /// The recording is on its way to the server, which is finding the tune.
  analyzing,

  /// The server is making the song.
  making,
}

/// Everything the hum page does: record a hum, find its tune, make the song
/// with the chosen engine, play it, edit it (genre, mood, chat, undo), and
/// save it. The page only draws this state and forwards taps.
class HumController extends ChangeNotifier
    with _BandEditing, _Saving
    implements ChatHost {
  HumController({
    HumRepository? repository,
    HumRecorder? recorder,
    SongPlayer? player,
    SongPlayer? rawPlayer,
    HumRecorder? chatRecorder,
    SongPlayer? voicePlayer,
    FileSharer sharer = const SystemFileSharer(),
    SavedHumStore? store,
    this.maxHum = const Duration(seconds: 15),
  }) : _repository = repository ?? const ServerHumRepository(),
       _store = store ?? FileSavedHumStore(),
       _recorder = recorder ?? MicRecorder(),
       _player = player ?? JustAudioSongPlayer() {
    band = BandSession(_repository);
    rawPlayback = RawPlaybackController(
      repository: _repository,
      player: rawPlayer ?? JustAudioSongPlayer(name: 'raw'),
      sharer: sharer,
      beforePlay:
          _player.stop, // the song and the raw hum never play over each other
    );
    chat = ChatController(
      repository: _repository,
      host: this,
      recorder: chatRecorder,
      voice: voicePlayer,
    );
    _playingSub = _player.playing.listen((playing) {
      if (playing == isPlaying) return;
      isPlaying = playing;
      _changed();
    });
  }

  @override
  final HumRepository _repository;
  @override
  final SavedHumStore _store;
  final HumRecorder _recorder;
  final SongPlayer _player;
  final Duration maxHum;

  /// "Play back my hum": the raw notes, played exactly as hummed.
  late final RawPlaybackController rawPlayback;

  /// The band engine's editable song and its history.
  @override
  late final BandSession band;

  /// Change the song by typing or saying it.
  @override
  late final ChatController chat;

  @override
  HumPhase phase = HumPhase.idle;
  @override
  HumUpload? hum;
  @override
  HumNotes notes = const HumNotes();
  @override
  SongSettings settings = const SongSettings();
  @override
  HumEngine engine = HumEngine.band;
  @override
  String? error;

  /// Something the app did on its own that the listener should know about,
  /// like switching engine. Shown until dismissed or replaced.
  String? notice;
  bool isPlaying = false;

  /// The last song made, so playing it again doesn't ask the server again.
  @override
  Uint8List? _song;

  /// The settings and engine [_song] was made with: what Save keeps.
  @override
  (SongSettings, HumEngine)? _songMadeWith;
  StreamSubscription<bool>? _playingSub;
  Timer? _maxHumTimer;
  @override
  int _job = 0;
  bool _disposed = false;

  bool get hasSong => _song != null;
  @override
  bool get isBusy => phase != HumPhase.idle;

  // ── Humming ──────────────────────────────────────────────────────────

  Future<void> startHum() async {
    if (isBusy) return;
    await _player.stop();
    await rawPlayback.stop();
    error = null;
    try {
      if (!await _recorder.requestPermission()) {
        error =
            'The microphone is off for this app. Turn it on in Settings to hum.';
        return _changed();
      }
      await _recorder.start();
    } on Exception catch (e) {
      error = "Couldn't start recording ($e).";
      return _changed();
    }
    phase = HumPhase.recording;
    _maxHumTimer = Timer(maxHum, stopHum);
    _changed();
  }

  Future<void> stopHum() async {
    if (phase != HumPhase.recording) return;
    _maxHumTimer?.cancel();
    final job = ++_job;
    phase = HumPhase.analyzing;
    _changed();
    try {
      final path = await _recorder.stop();
      if (path == null) {
        throw const ApiException('Nothing was recorded. Try again.');
      }
      final upload = await _repository.upload(path);
      if (job != _job) return;
      hum = upload;
      _song = null;
      savedThisSong = false;
      notes = const HumNotes();
      band.clear(); // a new hum is a new song
      unawaited(
        rawPlayback.load(upload),
      ); // reports its own errors on its panel
      await _remake(job);
    } on ApiException catch (e) {
      _fail(job, e.message);
    } on Exception catch (e) {
      _fail(job, "Couldn't use that recording ($e).");
    }
  }

  // ── Engine, genre, mood, faders ──────────────────────────────────────

  Future<void> setEngine(HumEngine next) async {
    if (next == engine) return;
    final left = engine;
    engine = next;
    notice = left == HumEngine.band && band.canUndo
        ? EngineNotices.leftEditedBand(next)
        : null;
    _changed();
    await _remakeIfHummed();
  }

  void dismissNotice() {
    notice = null;
    _changed();
  }

  /// A fader is moving: show it, but wait to make the song until it's let go.
  void moveFader({double? emotion, double? speed, double? pitch}) {
    settings = settings.copyWith(emotion: emotion, speed: speed, pitch: pitch);
    _changed();
  }

  /// A fader was let go.
  Future<void> commitSettings() => _remakeIfHummed();

  /// Epic and Simple: the faders back to the middle. Band: the song arranged
  /// afresh from the hum, as a step that can be undone.
  Future<void> resetSettings() async {
    settings = SongSettings(
      style: settings.style,
      mood: settings.mood,
      instruments: settings.instruments,
    );
    _changed();
    final current = hum;
    if (!_editingBand || current == null) return _remakeIfHummed();
    await _bandJob((job) async {
      final fresh = await _repository.project(current, settings);
      await _showBand(job, fresh, play: true, label: 'start over');
    });
  }

  // ── Playing ──────────────────────────────────────────────────────────

  Future<void> togglePlay() async {
    if (isPlaying) return _player.stop();
    await playSong();
  }

  @override
  Future<void> playSong() async {
    final song = _song;
    if (song == null) return;
    await rawPlayback.stop();
    await _player.playWav(song);
  }

  @override
  Future<void> stopSong() async {
    await _player.stop();
    await rawPlayback.stop();
  }

  // ── Making the song ──────────────────────────────────────────────────

  @override
  Future<void> _remakeIfHummed() async {
    if (hum == null || phase == HumPhase.recording) return;
    await _remake(++_job);
  }

  /// Makes the song and its notes again, then plays it. A newer request
  /// ([job] no longer current) quietly drops this one's result.
  Future<void> _remake(int job) async {
    final current = hum;
    if (current == null) return;
    phase = HumPhase.making;
    error = null;
    _changed();
    try {
      if (engine == HumEngine.band) {
        return await _makeBand(job, current, play: true);
      }
      final madeWith = (settings, engine);
      final results = await Future.wait<Object>([
        _repository.song(current, settings, engine),
        _repository.notes(current, settings, engine),
      ]);
      if (job != _job) return;
      _shown(results[0] as Uint8List, results[1] as HumNotes, madeWith);
      await playSong();
    } on ApiException catch (e) {
      _fail(job, e.message);
    } on Exception catch (e) {
      _fail(job, "Couldn't make the song ($e).");
    }
  }

  @override
  void _shown(
    Uint8List audio,
    HumNotes graph,
    (SongSettings, HumEngine) madeWith,
  ) {
    _song = audio;
    _songMadeWith = madeWith;
    savedThisSong = false;
    notes = graph;
    phase = HumPhase.idle;
    _changed();
  }

  // ── Plumbing ─────────────────────────────────────────────────────────

  @override
  void _fail(int job, String message) {
    if (job != _job) return;
    phase = HumPhase.idle;
    error = message;
    _changed();
  }

  @override
  void _changed() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _maxHumTimer?.cancel();
    _playingSub?.cancel();
    _recorder.dispose();
    _player.dispose();
    rawPlayback.dispose();
    chat.dispose();
    super.dispose();
  }
}
