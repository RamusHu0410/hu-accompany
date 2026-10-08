import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:hu_accomponist/features/hum/hum_controller.dart';
import 'package:hu_accomponist/features/hum/hum_page.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';

import 'support/hum_fakes.dart';

void main() {
  late FakeRecorder recorder;
  late FakeHumRepository repository;
  late HumController controller;
  late FakeSharer sharer;
  late MemorySavedHumStore store;

  setUp(() {
    recorder = FakeRecorder();
    repository = FakeHumRepository();
    sharer = FakeSharer();
    store = MemorySavedHumStore();
    controller = HumController(
      repository: repository,
      recorder: recorder,
      player: FakePlayer(),
      rawPlayer: FakePlayer(),
      sharer: sharer,
      store: store,
    );
  });

  tearDown(() => controller.dispose());

  Future<void> show(WidgetTester tester) async {
    tester.view.physicalSize = const Size(900, 4800);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(home: HumPage(controller: controller)));
  }

  Future<void> hum(WidgetTester tester) async {
    await tester.runAsync(() async {
      await controller.startHum();
      await controller.stopHum();
    });
    await tester.pump();
  }

  testWidgets('starts with just the hum button', (tester) async {
    await show(tester);

    expect(find.text('Hold to hum'), findsOneWidget);
    expect(find.text('Your notes will show up here'), findsOneWidget);
    expect(find.text('YOUR SONG'), findsNothing);
    expect(find.text('CHANGE IT WITH WORDS'), findsNothing);
  });

  testWidgets('shows the song, its controls and the chat once there is a hum', (
    tester,
  ) async {
    await show(tester);
    await hum(tester);

    expect(find.text('G major  ·  97 bpm  ·  9 notes'), findsOneWidget);
    expect(find.text('YOUR SONG'), findsOneWidget);
    expect(find.text('Band'), findsOneWidget);
    expect(find.text('Epic'), findsOneWidget);
    expect(find.text('Simple'), findsOneWidget);
    expect(find.text('Mood'), findsOneWidget);
    expect(find.text('GENRE'), findsOneWidget);
    expect(find.text('Lo-fi'), findsOneWidget);
    expect(find.text('CHANGE IT WITH WORDS'), findsOneWidget);
    expect(find.text('Your notes will show up here'), findsNothing);
  });

  testWidgets('picking Simple makes the song with the simple engine', (
    tester,
  ) async {
    await show(tester);
    await hum(tester);

    await tester.tap(find.text('Simple'));
    await tester.pump();
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 50)),
    );
    await tester.pump();

    expect(repository.songCalls.last.$1.apiName, 'simple');
  });

  testWidgets('the band engine has genres and moods to pick, the others not', (
    tester,
  ) async {
    await show(tester);
    await hum(tester);

    await tester.tap(find.byKey(const ValueKey('genre-Lo-fi')));
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 50)),
    );
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('mood-Chill')));
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 50)),
    );
    await tester.pump();

    final (engine, settings) = repository.songCalls.last;
    expect(engine, HumEngine.band);
    expect((settings.style, settings.mood), ('lofi', 'chill'));
    expect(
      tester
          .widget<ChoiceChip>(find.byKey(const ValueKey('genre-Lo-fi')))
          .selected,
      isTrue,
    );

    await tester.tap(find.text('Epic'));
    await tester.pump();
    expect(find.text('GENRE'), findsNothing);
  });

  testWidgets('Save keeps the song and says where it went', (tester) async {
    await show(tester);
    await hum(tester);

    await tester.tap(find.byKey(const ValueKey('save-song')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(store.songs, hasLength(1));
    expect(find.text('Saved to your shelf, under Hummed.'), findsOneWidget);
    expect(find.text('Saved'), findsOneWidget);
    final button = tester.widget<TextButton>(
      find.ancestor(
        of: find.text('Saved'),
        matching: find.byWidgetPredicate((w) => w is TextButton),
      ),
    );
    expect(button.onPressed, isNull);
  });

  testWidgets('a suggestion chip talks to the song and shows the reply', (
    tester,
  ) async {
    await show(tester);
    await hum(tester);

    await tester.tap(find.text('Make it faster'));
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 50)),
    );
    await tester.pump();

    expect(repository.talkTexts, ['Make it faster']);
    expect(find.text('A little quicker now!'), findsOneWidget);
  });

  testWidgets('a hum the server refuses shows why', (tester) async {
    repository.uploadError = silentHum;
    await show(tester);
    await hum(tester);

    expect(find.text(silentHum.message), findsOneWidget);
    expect(find.text('YOUR SONG'), findsNothing);
  });

  testWidgets('holding the button hums, and letting go finishes it', (
    tester,
  ) async {
    await show(tester);

    final hold = await tester.startGesture(
      tester.getCenter(find.byIcon(Icons.mic_rounded)),
    );
    await tester.pump(
      const Duration(milliseconds: 700),
    ); // past the long-press delay
    expect(find.text('Listening... let go when you are done'), findsOneWidget);

    await hold.up();
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 50)),
    );
    await tester.pump();

    expect(recorder.starts, 1);
    expect(repository.uploads, 1);
    expect(find.text('YOUR SONG'), findsOneWidget);
  });

  testWidgets('play my hum, switch to synth, and export MIDI from the page', (
    tester,
  ) async {
    await show(tester);
    await hum(tester);
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await tester.pump();

    expect(find.text('YOUR HUM, AS HUMMED'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('play-my-hum')));
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await tester.pump();
    expect(repository.rawAudioCalls, [RawInstrument.piano]);
    expect(find.text('Stop'), findsOneWidget);

    await tester.tap(find.text('Synth'));
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await tester.pump();
    expect(repository.rawAudioCalls.last, RawInstrument.synth);

    await tester.tap(find.text('Export MIDI'));
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await tester.pump();
    expect(sharer.shared.single.$1, 'hum.mid');
  });
}
