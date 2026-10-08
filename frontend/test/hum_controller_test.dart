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
    test('a hum becomes a song that plays, with its notes to draw', () async {
      await controller.startHum();
      expect(controller.phase, HumPhase.recording);
      expect(recorder.starts, 1);

      await controller.stopHum();

      expect(controller.phase, HumPhase.idle);
      expect(controller.hum?.filename, 'hum-1.wav');
      expect(controller.notes.sung, hasLength(1));
      expect(player.played, hasLength(1));
      expect(controller.error, isNull);
      expect(repository.songCalls.single.$1, HumEngine.band);
    });

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
    });

    test(
      'a fader shows its value at once, and remakes the song when let go',
      () async {
        await hum();
        controller.moveFader(speed: 0.9);
        controller.moveFader(speed: 0.95);

        expect(controller.settings.speed, 0.95);
        expect(repository.songCalls, hasLength(1));

        await controller.commitSettings();

        expect(repository.songCalls, hasLength(2));
        expect(repository.songCalls.last.$2.speed, 0.95);
      },
    );

    test('picking a genre remakes the song in it', () async {
      await hum();
      await controller.setGenre(SongGenre.lofi);

      expect(controller.genre, SongGenre.lofi);
      expect(repository.songCalls.last.$2.style, 'lofi');
      expect(player.played, hasLength(2));

      await controller.setGenre(
        SongGenre.lofi,
      ); // already chosen: nothing to do
      expect(repository.songCalls, hasLength(2));
    });

    test(
      'a mood is sent with the song, and picking it again clears it',
      () async {
        await hum();
        await controller.setMood(SongMood.hype);

        expect(controller.mood, SongMood.hype);
        expect(repository.songCalls.last.$2.toJson()['mood'], 'hype');

        await controller.setMood(SongMood.hype);

        expect(controller.mood, isNull);
        expect(
          repository.songCalls.last.$2.toJson().containsKey('mood'),
          isFalse,
        );
      },
    );

    test('reset keeps the genre and the mood', () async {
      await hum();
      await controller.setGenre(SongGenre.jazz);
      await controller.setMood(SongMood.dark);
      controller.moveFader(speed: 0.9);
      await controller.resetSettings();

      expect(
        (controller.genre, controller.mood),
        (SongGenre.jazz, SongMood.dark),
      );
      expect(controller.settings.speed, 0.5);
    });

    test('reset puts the faders back in the middle', () async {
      await hum();
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
      await controller.setGenre(SongGenre.lofi);

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

      expect(repository.songCalls, hasLength(1));
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

  group('chat', () {
    test(
      'a command that changes the song updates the settings and remakes it',
      () async {
        await hum();
        await controller.send('make it faster');

        expect(controller.chat.map((m) => m.fromUser), [true, false]);
        expect(controller.chat.last.text, 'A little quicker now!');
        expect(controller.settings.speed, 0.7);
        expect(repository.songCalls, hasLength(2));
        expect(repository.songCalls.last.$2.speed, 0.7);
      },
    );

    test(
      'a chat command keeps the mood the server does not know about',
      () async {
        // Talk mode's settings have no mood: the server sends them back without one.
        repository.onTalk = (text, settings) => FakeHumRepository.faster(
          text,
          SongSettings.fromJson(settings.toJson()..remove('mood')),
        );
        await hum();
        await controller.setMood(SongMood.chill);
        await controller.send('make it faster');

        expect(controller.settings.speed, 0.7);
        expect(controller.mood, SongMood.chill);
      },
    );

    test('small talk gets a reply and leaves the song alone', () async {
      repository.onTalk = FakeHumRepository.chatter;
      await hum();
      await controller.send('how are you?');

      expect(controller.chat.last.text, 'I only do music.');
      expect(repository.songCalls, hasLength(1));
      expect(controller.settings.speed, 0.5);
    });

    test(
      'works before there is a hum, just without a song to remake',
      () async {
        await controller.send('make it faster');

        expect(controller.settings.speed, 0.7);
        expect(repository.songCalls, isEmpty);
      },
    );

    test('a server error becomes a reply, not a crash', () async {
      repository.talkError = const ApiExceptionStub(
        'The voice service is down.',
      );
      await controller.send('faster');

      expect(controller.chat.last.fromUser, isFalse);
      expect(controller.chat.last.text, isNotEmpty);
      expect(controller.chatBusy, isFalse);
    });

    test('blank messages are ignored', () async {
      await controller.send('   ');
      expect(controller.chat, isEmpty);
      expect(repository.talkTexts, isEmpty);
    });
  });
}

/// Any error that isn't the app's own ApiException.
class ApiExceptionStub implements Exception {
  const ApiExceptionStub(this.message);
  final String message;
  @override
  String toString() => message;
}
