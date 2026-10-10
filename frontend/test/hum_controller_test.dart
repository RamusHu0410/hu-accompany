import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:hu_accomponist/features/hum/hum_controller.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/integrations/hum/song_style.dart';

import 'support/hum_fakes.dart';

void main() {
  late FakeRecorder recorder;
  late FakePlayer player;
  late FakeHumRepository repository;
  late MemorySavedHumStore store;
  late HumController controller;

  HumController build({Duration maxHum = const Duration(seconds: 15)}) =>
      HumController(
        repository: repository,
        recorder: recorder,
        player: player,
        rawPlayer: FakePlayer(),
        chatRecorder: FakeRecorder(),
        voicePlayer: FakePlayer(),
        sharer: FakeSharer(),
        store: store,
        maxHum: maxHum,
      );

  setUp(() {
    recorder = FakeRecorder();
    player = FakePlayer();
    repository = FakeHumRepository();
    store = MemorySavedHumStore();
    controller = build();
  });

  tearDown(() => controller.dispose());

  Future<void> hum() async {
    await controller.startHum();
    await controller.stopHum();
  }

  group('humming', () {
    test(
      'a hum becomes a band song that plays, with its notes to draw',
      () async {
        await controller.startHum();
        expect(controller.phase, HumPhase.recording);
        expect(recorder.starts, 1);

        await controller.stopHum();

        expect(controller.phase, HumPhase.idle);
        expect(controller.hum?.filename, 'hum-1.wav');
        expect(controller.notes.sung, hasLength(1));
        expect(player.played, hasLength(1));
        expect(controller.error, isNull);
        expect(controller.engine, HumEngine.band);
        expect(repository.projectCalls, hasLength(1)); // arranged once...
        expect(repository.renders, hasLength(1)); // ...and rendered
        expect(repository.songCalls, isEmpty);
        expect(controller.notes.played, hasLength(3));
      },
    );

    test('says so when the microphone is off, and does not record', () async {
      recorder.allowed = false;
      await controller.startHum();

      expect(controller.phase, HumPhase.idle);
      expect(recorder.starts, 0);
      expect(controller.error, contains('microphone'));
    });

    test("shows the server's reason when a hum can't be used", () async {
      repository.uploadError = silentHum;
      await hum();

      expect(controller.phase, HumPhase.idle);
      expect(controller.hum, isNull);
      expect(controller.error, silentHum.message);
      expect(player.played, isEmpty);
    });

    test('a new hum clears the last error', () async {
      repository.uploadError = silentHum;
      await hum();
      repository.uploadError = null;
      await hum();

      expect(controller.error, isNull);
      expect(controller.hum, isNotNull);
    });

    test('stops by itself when the hum runs long', () async {
      controller.dispose();
      player = FakePlayer(); // the first controller closed the old one
      controller = build(maxHum: const Duration(milliseconds: 20));
      await controller.startHum();
      await Future<void>.delayed(const Duration(milliseconds: 150));

      expect(controller.phase, HumPhase.idle);
      expect(controller.hum, isNotNull);
    });

    test('ignores a second press while busy', () async {
      await controller.startHum();
      await controller.startHum();
      expect(recorder.starts, 1);
    });

    test('nothing recorded is reported, not uploaded', () async {
      recorder.path = null;
      await hum();

      expect(repository.uploads, 0);
      expect(controller.error, contains('Nothing was recorded'));
    });
  });

  group('changing the song', () {
    test('switching engine remakes the song with it', () async {
      await hum();
      await controller.setEngine(HumEngine.simple);

      expect(repository.songCalls.last.$1, HumEngine.simple);
      expect(controller.notes.played, hasLength(1));
      expect(player.played, hasLength(2));
    });

    test('switching engine before any hum only remembers the choice', () async {
      await controller.setEngine(HumEngine.simple);

      expect(controller.engine, HumEngine.simple);
      expect(repository.songCalls, isEmpty);
      expect(repository.projectCalls, isEmpty);
    });

    test(
      'a fader shows its value at once, and remakes the song when let go',
      () async {
        await hum();
        await controller.setEngine(HumEngine.epic); // Band has no faders
        controller.moveFader(speed: 0.9);
        controller.moveFader(speed: 0.95);

        expect(controller.settings.speed, 0.95);
        expect(repository.songCalls, hasLength(1)); // the epic song

        await controller.commitSettings();

        expect(repository.songCalls, hasLength(2));
        expect(repository.songCalls.last.$2.speed, 0.95);
      },
    );

    test(
      'a genre picked before humming is the one the hum is arranged in',
      () async {
        await controller.setGenre(SongGenre.lofi);
        await hum();

        expect(controller.genre, SongGenre.lofi);
        expect(repository.projectCalls.single.style, 'lofi');
      },
    );

    test('reset puts the faders back in the middle', () async {
      await hum();
      await controller.setEngine(HumEngine.epic);
      controller.moveFader(speed: 0.9, pitch: 0.1);
      await controller.resetSettings();

      expect(controller.settings.speed, 0.5);
      expect(controller.settings.pitch, 0.5);
      expect(repository.songCalls.last.$2.speed, 0.5);
    });

    test('an older song never replaces a newer one', () async {
      await hum();
      repository.songGate = Completer<void>();

      final slow = controller.setEngine(HumEngine.simple);
      await Future<void>.delayed(Duration.zero);
      final fast = controller.setEngine(HumEngine.epic);
      await Future<void>.delayed(Duration.zero);
      repository.songGate!.complete();
      await Future.wait([slow, fast]);

      // Only the last request's song is played: the first hum's, then this one's.
      expect(player.played, hasLength(2));
      expect(controller.notes.played, hasLength(24)); // epic's
      expect(controller.engine, HumEngine.epic);
    });
  });

  group('saving', () {
    test('there is nothing to save before a song is made', () async {
      expect(controller.canSave, isFalse);
      expect(await controller.save(), isFalse);
      expect(store.songs, isEmpty);
    });

    test('one tap keeps the song, named for its genre and key', () async {
      await hum();
      expect(controller.canSave, isTrue);

      expect(await controller.save(), isTrue);

      final saved = store.songs.single;
      expect(saved.title, 'Cinematic hum in G major');
      expect((saved.engine, saved.humFilename), ('band', 'hum-1.wav'));
      expect(saved.sung, hasLength(1));
      expect(
        (await store.audioFor(saved)).readAsBytesSync(),
        player.played.last,
      );
      expect(controller.savedThisSong, isTrue);
      expect(controller.canSave, isFalse);
    });

    test('the same song is saved once', () async {
      await hum();
      await controller.save();
      expect(await controller.save(), isFalse);
      expect(store.songs, hasLength(1));
    });

    test('a changed song can be saved again, as a new one', () async {
      await hum();
      await controller.save();
      await controller.setGenre(SongGenre.lofi); // an edit of the band song

      expect(controller.canSave, isTrue);
      await controller.save();
      expect(store.songs.map((s) => s.title), [
        'Lo-fi hum in G major',
        'Cinematic hum in G major',
      ]);
      expect(store.songs.first.settings.style, 'lofi');
    });

    test('other engines are named after the engine', () async {
      await hum();
      await controller.setEngine(HumEngine.simple);
      await controller.save();
      expect(store.songs.single.title, 'Simple hum in G major');
    });

    test('a failed save says why and can be tried again', () async {
      await hum();
      store.fail = true;

      expect(await controller.save(), isFalse);
      expect(controller.error, contains("Couldn't save"));
      expect(controller.canSave, isTrue);
    });
  });

  group('playing', () {
    test('plays the song again without asking the server', () async {
      await hum();
      await player.stop();
      await controller.togglePlay();

      expect(repository.renders, hasLength(1));
      expect(player.played, hasLength(2));
    });

    test('stops a song that is playing', () async {
      await hum();
      await Future<void>.delayed(Duration.zero);
      expect(controller.isPlaying, isTrue);

      await controller.togglePlay();
      await Future<void>.delayed(Duration.zero);

      expect(controller.isPlaying, isFalse);
    });
  });
}
