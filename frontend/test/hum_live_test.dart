// Talks to a real backend, so it only runs when you point it at one:
//
//   cd backend && python manage.py runserver 8765
//   cd frontend && HUM_SERVER=http://127.0.0.1:8765 \
//       HUM_WAV=../backend/hum/tests/fixtures/hum_sample.wav flutter test test/hum_live_test.dart
//
// It checks the app's side of the contract against the backend's real answers:
// upload, both engines' songs and notes, and a typed command.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/integrations/hum/hum_repository.dart';
import 'package:hu_accomponist/integrations/server/ServerDiscovery.dart';
import 'package:hu_accomponist/integrations/server/api_client.dart';

void main() {
  final server = Platform.environment['HUM_SERVER'];
  final wav = Platform.environment['HUM_WAV'] ??
      '../backend/hum/tests/fixtures/hum_sample.wav';

  group('against a real backend', () {
    const repository = ServerHumRepository();
    late HumUpload hum;

    setUpAll(() async {
      ServerDiscovery.useBaseUrl(server!);
      hum = await repository.upload(wav);
    });

    test('finds the tune in a hum', () {
      expect(hum.filename, endsWith('.wav'));
      expect(hum.noteCount, greaterThan(2));
      expect(hum.tempo, greaterThan(0));
    });

    for (final engine in HumEngine.values) {
      test('${engine.label} makes a song and its notes', () async {
        const settings = SongSettings();
        final song = await repository.song(hum, settings, engine);
        final notes = await repository.notes(hum, settings, engine);

        expect(String.fromCharCodes(song.take(4)), 'RIFF');
        expect(song.length, greaterThan(10000));
        expect(notes.sung, isNotEmpty);
        expect(notes.played, isNotEmpty);
      });
    }

    test('a fader changes the song', () async {
      final slow = await repository.song(
        hum,
        const SongSettings(speed: 0),
        HumEngine.simple,
      );
      final fast = await repository.song(
        hum,
        const SongSettings(speed: 1),
        HumEngine.simple,
      );
      expect(slow.length, greaterThan(fast.length));
    });

    test('a typed command is answered, keys or no keys', () async {
      final turn = await repository.talk('make it faster', const SongSettings());

      expect(turn.reply, isNotEmpty);
      expect(turn.speechId, isNotEmpty);
    });

    test('the backend explains a hum that has no tune', () async {
      final silent = File('${Directory.systemTemp.path}/silent-hum.wav');
      final header = <int>[
        ...'RIFF'.codeUnits, 36 + 44100, 0, 0, 0, ...'WAVE'.codeUnits,
        ...'fmt '.codeUnits, 16, 0, 0, 0, 1, 0, 1, 0, 0x44, 0xAC, 0, 0,
        0x88, 0x58, 1, 0, 2, 0, 16, 0, ...'data'.codeUnits, 0x44, 0xAC, 0, 0,
      ];
      silent.writeAsBytesSync([...header, ...List.filled(44100, 0)]);

      await expectLater(
        repository.upload(silent.path),
        throwsA(
          isA<ApiException>()
              .having((e) => e.code, 'code', isNotNull)
              .having((e) => e.message, 'message', isNotEmpty),
        ),
      );
    });
  }, skip: server == null ? 'set HUM_SERVER to run against a backend' : false);
}
