import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:hu_accomponist/features/hum/hum_audio.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/integrations/hum/hum_repository.dart';
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
    this.maxHum = const Duration(seconds: 15),
  }) : _repository = repository ?? const ServerHumRepository(),
       _recorder = recorder ?? MicRecorder(),
       _player = player ?? JustAudioSongPlayer() {
    _playingSub = _player.playing.listen((playing) {
      if (playing == isPlaying) return;
      isPlaying = playing;
      notifyListeners();
    });
  }

  final HumRepository _repository;
  final HumRecorder _recorder;
  final SongPlayer _player;
  final Duration maxHum;

  HumPhase phase = HumPhase.idle;
  HumUpload? hum;
  HumNotes notes = const HumNotes();
  SongSettings settings = const SongSettings();
  HumEngine engine = HumEngine.epic;
  String? error;
  bool isPlaying = false;

  final List<ChatMessage> chat = [];
  bool chatBusy = false;

  /// The last song made, so playing it again doesn't ask the server again.
  Uint8List? _song;
  SongSettings? _previousSettings;
  StreamSubscription<bool>? _playingSub;
  Timer? _maxHumTimer;
  int _job = 0;
  bool _disposed = false;

  bool get hasSong => _song != null;
  bool get isBusy => phase != HumPhase.idle;

  // ── Humming ──────────────────────────────────────────────────────────

  Future<void> startHum() async {
    if (isBusy) return;
    await _player.stop();
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
      notes = const HumNotes();
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
      instruments: settings.instruments,
    );
    _changed();
    await _remakeIfHummed();
  }

  Future<void> togglePlay() async {
    if (isPlaying) return _player.stop();
    final song = _song;
    if (song != null) await _player.playWav(song);
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
      final results = await Future.wait<Object>([
        _repository.song(current, settings, engine),
        _repository.notes(current, settings, engine),
      ]);
      if (job != _job) return;
      _song = results[0] as Uint8List;
      notes = results[1] as HumNotes;
      phase = HumPhase.idle;
      _changed();
      await _player.playWav(_song!);
    } on ApiException catch (e) {
      _fail(job, e.message);
    } on Exception catch (e) {
      _fail(job, "Couldn't make the song ($e).");
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
        settings = turn.settings;
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
    super.dispose();
  }
}
