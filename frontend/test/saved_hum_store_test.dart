import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/integrations/hum/saved_hum_store.dart';

/// A 16-bit mono WAV of [seconds] of silence at [rate].
Uint8List wav(double seconds, {int rate = 8000}) {
  final data = (seconds * rate).round() * 2;
  final header = ByteData(44)
    ..setUint32(4, 36 + data, Endian.little)
    ..setUint16(22, 1, Endian.little)
    ..setUint32(24, rate, Endian.little)
    ..setUint16(34, 16, Endian.little);
  final bytes = Uint8List(44 + data)..setAll(0, header.buffer.asUint8List());
  bytes.setAll(0, 'RIFF'.codeUnits);
  return bytes;
}

SavedHum details(String title) => SavedHum(
  id: 'ignored',
  title: title,
  savedAt: DateTime(2026, 10, 8),
  style: 'Lo-fi',
  key: 'D',
  mode: 'minor',
  tempo: 90,
  seconds: 2,
  sung: const [HumNote(midi: 62, start: 0, duration: 0.5, velocity: 100)],
  engine: 'band',
  humFilename: 'hum-1.wav',
  settings: const SongSettings(style: 'lofi', mood: 'chill'),
);

void main() {
  late Directory folder;
  late FileSavedHumStore store;

  setUp(() {
    folder = Directory.systemTemp.createTempSync('saved-hums-');
    store = FileSavedHumStore(folder: () async => folder);
  });

  tearDown(() => folder.deleteSync(recursive: true));

  test('nothing saved yet is an empty list', () async {
    expect(await store.loadAll(), isEmpty);
  });

  test(
    'a saved song keeps its audio and everything about it, newest first',
    () async {
      final first = await store.save(wav(1), details('First'));
      final second = await store.save(wav(2), details('Second'));

      final songs = await store.loadAll();
      expect(songs.map((s) => s.title), ['Second', 'First']);
      expect(first.id, isNot('ignored'));
      expect(first.id, isNot(second.id));
      expect((await store.audioFor(second)).readAsBytesSync(), wav(2));

      final kept = songs.last;
      expect(
        (kept.style, kept.key, kept.mode, kept.tempo),
        ('Lo-fi', 'D', 'minor', 90),
      );
      expect(kept.sung.single.midi, 62);
      expect((kept.settings.style, kept.settings.mood), ('lofi', 'chill'));
      expect(kept.humFilename, 'hum-1.wav');
    },
  );

  test('saved songs survive the store being opened again', () async {
    await store.save(wav(1), details('Kept'));
    final reopened = FileSavedHumStore(folder: () async => folder);
    expect((await reopened.loadAll()).single.title, 'Kept');
  });

  test('renaming changes only the title', () async {
    final song = await store.save(wav(1), details('Old'));
    await store.rename(song.id, 'New');
    final renamed = (await store.loadAll()).single;
    expect((renamed.id, renamed.title, renamed.key), (song.id, 'New', 'D'));
  });

  test('deleting removes the song and its audio', () async {
    final gone = await store.save(wav(1), details('Gone'));
    await store.save(wav(1), details('Stays'));
    final audio = await store.audioFor(gone);

    await store.delete(gone.id);

    expect((await store.loadAll()).map((s) => s.title), ['Stays']);
    expect(audio.existsSync(), isFalse);
  });

  test('a damaged index reads as empty instead of failing', () async {
    File('${folder.path}/index.json').writeAsStringSync('{not json');
    expect(await store.loadAll(), isEmpty);
  });

  test('a WAV says how long it plays; anything else is 0', () {
    expect(wavSeconds(wav(2.5)), closeTo(2.5, 0.001));
    expect(wavSeconds(Uint8List.fromList([1, 2, 3])), 0);
  });
}
