import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:hu_accomponist/features/hum/file_sharer.dart';
import 'package:hu_accomponist/features/hum/hum_audio.dart';
import 'package:hu_accomponist/features/hum/raw_playback_controller.dart';
import 'package:hu_accomponist/features/hum/song_saving.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/integrations/hum/hum_repository.dart';
import 'package:hu_accomponist/integrations/hum/saved_hum_store.dart';
import 'package:hu_accomponist/integrations/hum/song_style.dart';
import 'package:hu_accomponist/integrations/server/api_client.dart';

/// What the hum page is busy with.
enum HumPhase {
  idle,
  recording,

  /// The recording is on its way to the server, which is finding the tune.
  analyzing,

  /// The server is making the song.
  making,
}

class ChatMessage {
  final bool fromUser;
  final String text;
  const ChatMessage({required this.fromUser, required this.text});
}

/// Everything the hum page does: record a hum, find its tune, make the song
/// with the chosen engine, play it, and change it with the faders or by chat.
/// The page only draws this state and forwards taps.
class HumController extends ChangeNotifier {
  HumController({
    HumRepository? repository,
    HumRecorder? recorder,
    SongPlayer? player,
    SongPlayer? rawPlayer,
    FileSharer sharer = const SystemFileSharer(),
    SavedHumStore? store,
    this.maxHum = const Duration(seconds: 15),
  }) : _repository = repository ?? const ServerHumRepository(),
       _store = store ?? FileSavedHumStore(),
       _recorder = recorder ?? MicRecorder(),
       _player = player ?? JustAudioSongPlayer() {
    rawPlayback = RawPlaybackController(
      repository: _repository,
      player: rawPlayer ?? JustAudioSongPlayer(name: 'raw'),
      sharer: sharer,
      beforePlay:
          _player.stop, // the song and the raw hum never play over each other
    );
    _playingSub = _player.playing.listen((playing) {
      if (playing == isPlaying) return;
      isPlaying = playing;
      notifyListeners();
    });
  }

  final HumRepository _repository;
  final SavedHumStore _store;
  final HumRecorder _recorder;
  final SongPlayer _player;
  final Duration maxHum;

  /// "Play back my hum": the raw notes, played exactly as hummed.
  late final RawPlaybackController rawPlayback;

  HumPhase phase = HumPhase.idle;
  HumUpload? hum;
  HumNotes notes = const HumNotes();
  SongSettings settings = const SongSettings();
  HumEngine engine = HumEngine.band;
  String? error;
  bool isPlaying = false;

  final List<ChatMessage> chat = [];
  bool chatBusy = false;

  /// The last song made, so playing it again doesn't ask the server again.
  Uint8List? _song;

  /// The settings and engine [_song] was made with: what Save keeps.
  (SongSettings, HumEngine)? _songMadeWith;

  bool saving = false;

  /// Whether the song as it is now is already on the shelf.
  bool savedThisSong = false;
  SongSettings? _previousSettings;
  StreamSubscription<bool>? _playingSub;
  Timer? _maxHumTimer;
  int _job = 0;
  bool _disposed = false;

  bool get hasSong => _song != null;
  bool get canSave =>
      _song != null && phase == HumPhase.idle && !saving && !savedThisSong;
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

  // ── The song ─────────────────────────────────────────────────────────

  Future<void> setEngine(HumEngine next) async {
    if (next == engine) return;
    engine = next;
    _changed();
    await _remakeIfHummed();
  }

  /// The band engine's genre.
  SongGenre? get genre => SongGenre.fromStyle(settings.style);

  /// The band engine's mood; null is "as hummed".
  SongMood? get mood => SongMood.fromName(settings.mood);

  Future<void> setGenre(SongGenre next) async {
    if (next == genre) return;
    settings = settings.withStyle(next.apiName);
    _changed();
    await _remakeIfHummed();
  }

  /// Picking the mood that's already chosen goes back to "as hummed".
  Future<void> setMood(SongMood? next) async {
    settings = settings.withMood(next == mood ? null : next?.apiName);
    _changed();
    await _remakeIfHummed();
  }

  /// A fader is moving: show it, but wait to make the song until it's let go.
  void moveFader({double? emotion, double? speed, double? pitch}) {
    settings = settings.copyWith(emotion: emotion, speed: speed, pitch: pitch);
    _changed();
  }

  /// A fader was let go.
  Future<void> commitSettings() => _remakeIfHummed();

  Future<void> resetSettings() async {
    settings = SongSettings(
      style: settings.style,
      mood: settings.mood,
      instruments: settings.instruments,
    );
    _changed();
    await _remakeIfHummed();
  }

  Future<void> togglePlay() async {
    if (isPlaying) return _player.stop();
    final song = _song;
    if (song == null) return;
    await rawPlayback.stop();
    await _player.playWav(song);
  }

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
      final madeWith = (settings, engine);
      final results = await Future.wait<Object>([
        _repository.song(current, settings, engine),
        _repository.notes(current, settings, engine),
      ]);
      if (job != _job) return;
      _song = results[0] as Uint8List;
      _songMadeWith = madeWith;
      savedThisSong = false;
      notes = results[1] as HumNotes;
      phase = HumPhase.idle;
      _changed();
      await rawPlayback.stop();
      await _player.playWav(_song!);
    } on ApiException catch (e) {
      _fail(job, e.message);
    } on Exception catch (e) {
      _fail(job, "Couldn't make the song ($e).");
    }
  }

  // ── Keeping it ───────────────────────────────────────────────────────

  /// Saves the song as it is now to the shelf, named for its style and key.
  /// True when it was saved.
  Future<bool> save() async {
    final song = _song, current = hum, madeWith = _songMadeWith;
    if (!canSave || song == null || current == null || madeWith == null) {
      return false;
    }
    saving = true;
    _changed();
    try {
      final (madeSettings, madeEngine) = madeWith;
      await _store.save(
        song,
        songToSave(
          song: song,
          hum: current,
          settings: madeSettings,
          engine: madeEngine,
          sung: notes.sung,
        ),
      );
      savedThisSong = true;
      return true;
    } on Exception catch (e) {
      error = "Couldn't save the song ($e).";
      return false;
    } finally {
      saving = false;
      _changed();
    }
  }

  // ── Talking to it ────────────────────────────────────────────────────

  Future<void> send(String text) async {
    final words = text.trim();
    if (words.isEmpty || chatBusy) return;
    chat.add(ChatMessage(fromUser: true, text: words));
    chatBusy = true;
    _changed();
    try {
      final turn = await _repository.talk(
        words,
        settings,
        previous: _previousSettings,
      );
      chat.add(ChatMessage(fromUser: false, text: _replyText(turn)));
      if (turn.changesSong) {
        _previousSettings = settings;
        settings = turn.settings.withMood(
          settings.mood,
        ); // talk mode has no moods
      }
      chatBusy = false;
      _changed();
      if (turn.changesSong) await _remakeIfHummed();
    } on ApiException catch (e) {
      chat.add(ChatMessage(fromUser: false, text: e.message));
      chatBusy = false;
      _changed();
    } on Exception catch (e) {
      chat.add(
        ChatMessage(fromUser: false, text: "I couldn't reach the server ($e)."),
      );
      chatBusy = false;
      _changed();
    }
  }

  String _replyText(TalkTurn turn) {
    if (turn.reply.isNotEmpty) return turn.reply;
    return turn.error ?? "I didn't catch that. Try again?";
  }

  // ── Plumbing ─────────────────────────────────────────────────────────

  void _fail(int job, String message) {
    if (job != _job) return;
    phase = HumPhase.idle;
    error = message;
    _changed();
  }

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
    super.dispose();
  }
}
