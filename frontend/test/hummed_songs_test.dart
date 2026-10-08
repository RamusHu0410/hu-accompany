import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:hu_accomponist/features/shelf/Shelf_Page.dart';
import 'package:hu_accomponist/features/shelf/hummed_songs_controller.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/integrations/hum/saved_hum_store.dart';

import 'support/hum_fakes.dart';

SavedHum details(String title) => SavedHum(
  id: '',
  title: title,
  savedAt: DateTime.now(),
  style: 'Jazz',
  key: 'G',
  mode: 'major',
  tempo: 97,
  seconds: 65,
  sung: const [HumNote(midi: 67, start: 0, duration: 1)],
  engine: 'band',
  humFilename: 'hum-1.wav',
  settings: const SongSettings(style: 'jazz'),
);

/// Lets an animation (a tab sliding, a menu opening) run to its end.
Future<void> settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
  await tester.pump();
}

void main() {
  late MemorySavedHumStore store;
  late FakePlayer player;
  late HummedSongsController controller;

  setUp(() async {
    store = MemorySavedHumStore();
    player = FakePlayer();
    controller = HummedSongsController(store: store, player: player);
    await store.save(Uint8List.fromList([1]), details('Older'));
    await store.save(Uint8List.fromList([2]), details('Newer'));
  });

  tearDown(() => controller.dispose());

  group('the controller', () {
    test('loads the saved songs, newest first', () async {
      await controller.load();
      expect(controller.loading, isFalse);
      expect(controller.songs.map((s) => s.title), ['Newer', 'Older']);
    });

    test('plays one song at a time, and a second tap stops it', () async {
      await controller.load();
      final newer = controller.songs.first, older = controller.songs.last;

      await controller.toggle(newer);
      expect(controller.playingId, newer.id);

      await controller.toggle(older);
      expect(controller.playingId, older.id);

      await controller.toggle(older);
      expect(controller.playingId, isNull);
    });

    test('forgets the playing song when it finishes', () async {
      await controller.load();
      await controller.toggle(controller.songs.first);
      await Future<void>.delayed(Duration.zero); // "playing" arrives
      await player.stop(); // as the end of the song does
      await Future<void>.delayed(Duration.zero);
      expect(controller.playingId, isNull);
    });

    test('says so when a song\'s audio is missing', () async {
      await controller.load();
      final song = controller.songs.first;
      (await store.audioFor(song)).deleteSync();
      await controller.toggle(song);
      expect(controller.playingId, isNull);
      expect(controller.error, contains('missing'));
    });

    test('renames, ignoring a blank name, and deletes', () async {
      await controller.load();
      await controller.rename(controller.songs.first, '   ');
      expect(controller.songs.first.title, 'Newer');
      await controller.rename(controller.songs.first, 'My tune');
      expect(controller.songs.first.title, 'My tune');

      await controller.toggle(controller.songs.first);
      await controller.delete(controller.songs.first);
      expect(controller.songs.map((s) => s.title), ['Older']);
      expect(controller.playingId, isNull);
    });
  });

  group('the shelf', () {
    Future<void> show(WidgetTester tester, {int tab = 0}) async {
      SharedPreferences.setMockInitialValues({});
      await tester.pumpWidget(
        MaterialApp(
          home: Shelf_Page(hummed: controller, initialTab: tab),
        ),
      );
      await tester.pump();
      await settle(tester);
    }

    testWidgets('has a Sheets tab and a Hummed tab', (tester) async {
      await show(tester);
      expect(find.text('Sheets'), findsOneWidget);
      expect(find.text('Hummed'), findsOneWidget);
      expect(
        find.text('Your shelf is empty'),
        findsOneWidget,
      ); // no sheets opened

      await tester.tap(find.text('Hummed'));
      await settle(tester);
      expect(find.text('Newer'), findsOneWidget);
      expect(
        find.text('Jazz  ·  G major  ·  1:05  ·  Just now'),
        findsNWidgets(2),
      );
    });

    testWidgets('tapping a hummed song plays it', (tester) async {
      await show(tester, tab: 1);
      await tester.tap(find.text('Newer'));
      await tester.pump();
      expect(controller.playingId, controller.songs.first.id);
      expect(find.byIcon(Icons.stop_rounded), findsOneWidget);
    });

    testWidgets('a hummed song can be deleted from its menu', (tester) async {
      await show(tester, tab: 1);
      final newer = controller.songs.first;
      await tester.tap(find.byKey(ValueKey('hummed-menu-${newer.id}')));
      await settle(tester);
      await tester.tap(find.text('Delete'));
      await settle(tester);
      await tester.tap(find.widgetWithText(TextButton, 'Delete'));
      await settle(tester);

      expect(find.text('Newer'), findsNothing);
      expect(find.text('Older'), findsOneWidget);
    });

    testWidgets('with nothing saved, says how to save one', (tester) async {
      store.songs.clear();
      await show(tester, tab: 1);
      expect(find.text('No hummed songs yet'), findsOneWidget);
    });
  });
}
