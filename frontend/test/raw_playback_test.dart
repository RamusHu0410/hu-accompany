import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:hu_accomponist/features/hum/hum_controller.dart';
import 'package:hu_accomponist/features/hum/raw_playback_controller.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';

import 'support/hum_fakes.dart';

const upload = HumUpload(
  filename: 'hum-1.wav',
  noteCount: 3,
  tempo: 92,
  key: 'D',
  mode: 'minor',
);

void main() {
  late FakeHumRepository repository;
  late FakePlayer player;
  late FakeSharer sharer;
  late RawPlaybackController playback;
  late int stopsBeforePlay;

  setUp(() {
    repository = FakeHumRepository();
    player = FakePlayer();
    sharer = FakeSharer();
    stopsBeforePlay = 0;
    playback = RawPlaybackController(
      repository: repository,
      player: player,
      sharer: sharer,
      beforePlay: () async => stopsBeforePlay++,
    );
  });

  tearDown(() => playback.dispose());

  Future<void> settle() => Future<void>.delayed(Duration.zero);

  test('loads the raw notes of a hum', () async {
    expect(playback.canPlay, isFalse);
    await playback.load(upload);

    expect(playback.hum?.notes, hasLength(3));
    expect(playback.canPlay, isTrue);
    expect(playback.loading, isFalse);
  });

  test("says why when the notes can't be loaded", () async {
    repository.rawError = silentHum;
    await playback.load(upload);

    expect(playback.hum, isNull);
    expect(playback.error, silentHum.message);
  });

  test(
    'plays the raw notes, after stopping whatever else was playing',
    () async {
      await playback.load(upload);
      await playback.play();

      expect(stopsBeforePlay, 1);
      expect(player.played.single, [100 + RawInstrument.piano.index]);
      expect(repository.rawAudioCalls, [RawInstrument.piano]);
    },
  );

  test('fetches each instrument once and replays it from memory', () async {
    await playback.load(upload);
    await playback.play();
    await playback.stop();
    await playback.play();

    expect(repository.rawAudioCalls, [RawInstrument.piano]);
    expect(player.played, hasLength(2));
  });

  test('switching to synth while playing carries on, on the synth', () async {
    await playback.load(upload);
    await playback.play();
    await settle();
    expect(playback.isPlaying, isTrue);

    await playback.setInstrument(RawInstrument.synth);

    expect(repository.rawAudioCalls, [
      RawInstrument.piano,
      RawInstrument.synth,
    ]);
    expect(player.played.last, [100 + RawInstrument.synth.index]);
  });

  test('switching instrument while stopped only remembers it', () async {
    await playback.load(upload);
    await playback.setInstrument(RawInstrument.synth);

    expect(playback.instrument, RawInstrument.synth);
    expect(player.played, isEmpty);
  });

  test('lights up the notes sounding at the playhead', () async {
    await playback.load(upload);
    await playback.play();
    await settle();

    player.emitPosition(const Duration(milliseconds: 300));
    await settle();
    expect(playback.sounding, {0});

    player.emitPosition(const Duration(milliseconds: 1500));
    await settle();
    expect(playback.sounding, {2});
    expect(playback.position, closeTo(1.5, 1e-9));

    player.emitPosition(const Duration(seconds: 3)); // after the last note
    await settle();
    expect(playback.sounding, isEmpty);
  });

  test('nothing is lit when playback stops', () async {
    await playback.load(upload);
    await playback.play();
    await settle();
    player.emitPosition(const Duration(milliseconds: 300));
    await playback.stop();
    await settle();

    expect(playback.isPlaying, isFalse);
    expect(playback.sounding, isEmpty);
    expect(playback.position, 0);
  });

  test('exports the raw notes as hum.mid through the share sheet', () async {
    await playback.load(upload);
    await playback.exportMidi();

    expect(sharer.shared.single.$1, 'hum.mid');
    expect(sharer.shared.single.$2, 'audio/midi');
    expect(playback.exporting, isFalse);
  });

  test('a newer hum replaces an older one still loading', () async {
    final gate = Completer<void>();
    final slow = FakeHumRepository();
    final first = RawPlaybackController(
      repository: _Gated(slow, gate),
      player: FakePlayer(),
      sharer: sharer,
    );
    final loadingOld = first.load(upload);
    await first.load(
      const HumUpload(
        filename: 'hum-2.wav',
        noteCount: 3,
        tempo: 92,
        key: 'D',
        mode: 'minor',
      ),
    );
    gate.complete();
    await loadingOld;

    expect(first.hum, isNotNull);
    expect(first.loading, isFalse);
    first.dispose();
  });

  group('on the hum page', () {
    late FakePlayer songPlayer;
    late FakePlayer rawPlayer;
    late HumController controller;

    setUp(() {
      songPlayer = FakePlayer();
      rawPlayer = FakePlayer();
      controller = HumController(
        repository: repository,
        recorder: FakeRecorder(),
        player: songPlayer,
        rawPlayer: rawPlayer,
        chatRecorder: FakeRecorder(),
        voicePlayer: FakePlayer(),
        sharer: sharer,
        store: MemorySavedHumStore(),
      );
    });

    tearDown(() => controller.dispose());

    Future<void> hum() async {
      await controller.startHum();
      await controller.stopHum();
      await settle();
    }

    test('a new hum loads its raw notes', () async {
      await hum();
      expect(controller.rawPlayback.hum?.notes, hasLength(3));
    });

    test(
      'playing the raw hum stops the song, and playing the song stops the raw hum',
      () async {
        await hum(); // the song starts playing
        final songStops = songPlayer.stops;

        await controller.rawPlayback.play();
        await settle();
        expect(songPlayer.stops, songStops + 1);
        expect(controller.rawPlayback.isPlaying, isTrue);

        await controller.togglePlay();
        await settle();
        expect(controller.rawPlayback.isPlaying, isFalse);
      },
    );
  });
}

/// Holds `raw` for the first hum until [gate] opens, like a slow network.
class _Gated extends FakeHumRepository {
  _Gated(this.inner, this.gate);

  final FakeHumRepository inner;
  final Completer<void> gate;

  @override
  Future<RawHum> raw(HumUpload hum) async {
    if (hum.filename == 'hum-1.wav') await gate.future;
    return inner.raw(hum);
  }
}
