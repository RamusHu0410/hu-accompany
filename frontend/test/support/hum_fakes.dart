import 'dart:async';
import 'dart:typed_data';

import 'dart:ui';

import 'package:hu_accomponist/features/hum/file_sharer.dart';
import 'package:hu_accomponist/features/hum/hum_audio.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/integrations/hum/hum_repository.dart';
import 'package:hu_accomponist/integrations/server/api_client.dart';

class FakeRecorder implements HumRecorder {
  FakeRecorder({this.allowed = true, this.path = '/tmp/hum.wav'});

  bool allowed;
  String? path;
  int starts = 0;
  bool disposed = false;

  @override
  Future<bool> requestPermission() async => allowed;

  @override
  Future<void> start() async => starts++;

  @override
  Future<String?> stop() async => path;

  @override
  Future<void> dispose() async => disposed = true;
}

class FakePlayer implements SongPlayer {
  final StreamController<bool> _playing = StreamController<bool>.broadcast();
  final StreamController<Duration> _position =
      StreamController<Duration>.broadcast();

  @override
  Stream<Duration> get position => _position.stream;

  /// Moves the playhead, as the real player does while playing.
  void emitPosition(Duration at) => _position.add(at);
  final List<Uint8List> played = [];
  int stops = 0;

  @override
  Stream<bool> get playing => _playing.stream;

  @override
  Future<void> playWav(Uint8List bytes) async {
    played.add(bytes);
    _playing.add(true);
  }

  @override
  Future<void> playUrl(Uri url) async => _playing.add(true);

  @override
  Future<void> stop() async {
    stops++;
    _playing.add(false);
  }

  @override
  Future<void> dispose() async {
    await _playing.close();
    await _position.close();
  }
}

class FakeSharer implements FileSharer {
  final List<(String, String, int)> shared = [];

  @override
  Future<void> share(
    Uint8List bytes, {
    required String filename,
    required String mimeType,
    Rect? origin,
  }) async => shared.add((filename, mimeType, bytes.length));
}

/// A server that answers instantly unless a test holds a call back.
class FakeHumRepository implements HumRepository {
  Object? uploadError;
  Object? talkError;
  TalkTurn Function(String text, SongSettings settings)? onTalk;

  /// When set, `song` waits for this before answering.
  Completer<void>? songGate;

  final List<(HumEngine, SongSettings)> songCalls = [];
  final List<String> talkTexts = [];
  int uploads = 0;
  int songNumber = 0;

  @override
  Future<HumUpload> upload(String wavPath) async {
    uploads++;
    if (uploadError != null) throw uploadError!;
    return const HumUpload(
      filename: 'hum-1.wav',
      noteCount: 9,
      tempo: 97,
      key: 'G',
      mode: 'major',
    );
  }

  @override
  Future<Uint8List> song(
    HumUpload hum,
    SongSettings settings,
    HumEngine engine,
  ) async {
    songCalls.add((engine, settings));
    final number = ++songNumber;
    await songGate?.future;
    return Uint8List.fromList([number]);
  }

  @override
  Future<HumNotes> notes(
    HumUpload hum,
    SongSettings settings,
    HumEngine engine,
  ) async {
    // The engine decides how many notes the song plays, so tests can tell
    // which request a result came from.
    final played = engine == HumEngine.epic ? 24 : 1;
    return HumNotes(
      sung: const [HumNote(midi: 60, start: 0, duration: 0.5)],
      played: [
        for (var i = 0; i < played; i++)
          HumNote(midi: 60, start: i * 0.1, duration: 0.1),
      ],
    );
  }

  @override
  Future<TalkTurn> talk(
    String text,
    SongSettings settings, {
    SongSettings? previous,
  }) async {
    talkTexts.add(text);
    if (talkError != null) throw talkError!;
    return (onTalk ?? faster)(text, settings);
  }

  Object? rawError;
  final List<RawInstrument> rawAudioCalls = [];
  int rawCalls = 0;

  static const RawHum rawHum = RawHum(
    notes: [
      HumNote(midi: 50, start: 0, duration: 0.6, velocity: 100),
      HumNote(midi: 52, start: 0.6, duration: 0.6, velocity: 80),
      HumNote(midi: 53, start: 1.2, duration: 1.0, velocity: 110),
    ],
    tempo: 92,
    key: 'D',
    mode: 'minor',
    duration: 2.2,
  );

  @override
  Future<RawHum> raw(HumUpload hum) async {
    rawCalls++;
    if (rawError != null) throw rawError!;
    return rawHum;
  }

  @override
  Future<Uint8List> rawAudio(HumUpload hum, RawInstrument instrument) async {
    rawAudioCalls.add(instrument);
    return Uint8List.fromList([100 + instrument.index]);
  }

  @override
  Future<Uint8List> rawMidi(HumUpload hum) async =>
      Uint8List.fromList('MThd'.codeUnits);

  @override
  Future<Uri> speechUrl(String speechId) async =>
      Uri.parse('http://test/speech/$speechId');

  static TalkTurn faster(String text, SongSettings settings) => TalkTurn(
    heard: text,
    intent: 'adjust',
    settings: settings.copyWith(speed: 0.7),
    changed: const ['speed'],
    reply: 'A little quicker now!',
    error: null,
    speechId: 'r1',
  );

  static TalkTurn chatter(String text, SongSettings settings) => TalkTurn(
    heard: text,
    intent: 'off_topic',
    settings: settings,
    changed: const [],
    reply: 'I only do music.',
    error: null,
    speechId: 'r2',
  );
}

const ApiException silentHum = ApiException(
  "I couldn't hear anything. Hum a little louder.",
  code: 'silent',
  status: 400,
);
