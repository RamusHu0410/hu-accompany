import 'package:flutter_test/flutter_test.dart';

import 'package:hu_accomponist/features/hum/chat_controller.dart';
import 'package:hu_accomponist/features/hum/engine_guide.dart';
import 'package:hu_accomponist/features/hum/hum_controller.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/integrations/hum/song_style.dart';

import 'support/hum_fakes.dart';

/// The band song as one editable project: genre and mood edit it, every
/// edit can be undone, and the app says so whenever it changes engine.
void main() {
  late FakePlayer player;
  late FakeHumRepository repository;
  late HumController controller;

  setUp(() {
    player = FakePlayer();
    repository = FakeHumRepository();
    controller = HumController(
      repository: repository,
      recorder: FakeRecorder(),
      player: player,
      rawPlayer: FakePlayer(),
      chatRecorder: FakeRecorder(),
      voicePlayer: FakePlayer(),
      sharer: FakeSharer(),
      store: MemorySavedHumStore(),
    );
  });

  tearDown(() => controller.dispose());

  Future<void> hum() async {
    await controller.startHum();
    await controller.stopHum();
  }

  group('genre and mood edit the song', () {
    test('a new genre is an edit of the song, not a new arrangement', () async {
      await hum();
      await controller.setGenre(SongGenre.jazz);

      expect(
        repository.projectCalls,
        hasLength(1),
      ); // only the first arrangement
      expect(repository.editCalls.single, [
        {'action': 'set_genre', 'genre': 'jazz'},
      ]);
      expect(controller.genre, SongGenre.jazz);
      expect(controller.band.project!.preset, 'jazz');
      expect(player.played, hasLength(2));
      expect(controller.undoLabel, 'jazz now');
    });

    test('picking the chosen mood again goes back to as hummed', () async {
      await hum();
      await controller.setMood(SongMood.dark);
      expect(controller.mood, SongMood.dark);
      await controller.setMood(SongMood.dark);
      expect(controller.mood, isNull);
      expect(repository.editCalls.last.single['mood'], 'neutral');
    });
  });

  group('undo and redo', () {
    test(
      'step back and forward through every version, and play each',
      () async {
        await hum();
        await controller.setGenre(SongGenre.rock);
        await controller.setGenre(SongGenre.jazz);

        await controller.undo();
        expect(controller.genre, SongGenre.rock);
        expect(controller.redoLabel, 'jazz now');
        await controller.undo();
        expect(controller.genre, isNot(SongGenre.rock));
        expect(controller.canUndo, isFalse);

        await controller.redo();
        await controller.redo();
        expect(controller.genre, SongGenre.jazz);
        expect(controller.canRedo, isFalse);
        expect(
          player.played,
          hasLength(7),
        ); // the first song, two edits, four steps
      },
    );

    test(
      'a step whose song fails to render leaves the history where it was',
      () async {
        await hum();
        await controller.setGenre(SongGenre.rock);
        repository.renderError = Exception('render failed');

        await controller.undo();

        expect(controller.genre, SongGenre.rock);
        expect(controller.canUndo, isTrue);
        expect(controller.error, contains('render failed'));
      },
    );

    test(
      'start over arranges the hum afresh, and can itself be undone',
      () async {
        await hum();
        await controller.setGenre(SongGenre.rock);
        await controller.resetSettings();

        expect(repository.projectCalls, hasLength(2));
        expect(controller.undoLabel, 'start over');
        await controller.undo();
        expect(controller.genre, SongGenre.rock);
      },
    );

    test('a new hum is a new song with a new history', () async {
      await hum();
      await controller.setGenre(SongGenre.rock);
      await hum();
      expect(controller.canUndo, isFalse);
    });
  });

  group('switching engines says so', () {
    test('leaving an edited band song keeps it, and says so', () async {
      await hum();
      await controller.setGenre(SongGenre.lofi);
      await controller.setEngine(HumEngine.epic);

      expect(controller.notice, EngineNotices.leftEditedBand(HumEngine.epic));
      expect(controller.canUndo, isFalse); // nothing to undo in Epic

      await controller.setEngine(HumEngine.band);
      expect(controller.genre, SongGenre.lofi); // the edits are back
      expect(repository.projectCalls, hasLength(1)); // without arranging again
      expect(controller.canUndo, isTrue);
    });

    test('leaving an unedited band song needs no notice', () async {
      await hum();
      await controller.setEngine(HumEngine.simple);
      expect(controller.notice, isNull);
    });

    test('chatting on Epic switches to Band first and says why', () async {
      await hum();
      await controller.setEngine(HumEngine.epic);
      await controller.chat.send('softer drums');

      expect(controller.engine, HumEngine.band);
      expect(controller.notice, EngineNotices.switchedForChat);
      final notices = controller.chat.entries.where(
        (e) => e.speaker == ChatSpeaker.notice,
      );
      expect(notices.single.text, EngineNotices.switchedForChat);
      expect(
        controller.band.project!.track('drums')!.volume,
        closeTo(0.4, 1e-9),
      );
      expect(controller.chat.entries.last.text, 'Drums are softer now.');
    });

    test('a notice can be dismissed', () async {
      await hum();
      await controller.setGenre(SongGenre.rock);
      await controller.setEngine(HumEngine.epic);
      controller.dismissNotice();
      expect(controller.notice, isNull);
    });

    test('every engine explains itself, and only Band takes chat edits', () {
      for (final engine in HumEngine.values) {
        expect(engine.summary, isNotEmpty);
        expect(engine.howItWorks, isNotEmpty);
        expect(engine.youCanChange, isNotEmpty);
      }
      expect(HumEngine.values.where((e) => e.editableByChat), [HumEngine.band]);
    });
  });
}
