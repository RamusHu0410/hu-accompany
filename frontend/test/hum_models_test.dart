import 'package:flutter_test/flutter_test.dart';

import 'package:hu_accomponist/integrations/hum/hum_models.dart';

void main() {
  test('settings survive a trip to the server and back', () {
    const settings = SongSettings(
      emotion: 0.2,
      speed: 0.8,
      pitch: 0.4,
      style: 'jazz',
      instruments: [
        Instrument(name: 'piano', role: 'lead', level: 'normal'),
        Instrument(name: 'violin', section: 'end'),
      ],
      energyStart: -1,
      energyEnd: 2,
    );

    final again = SongSettings.fromJson(settings.toJson());

    expect(again.toJson(), settings.toJson());
    expect(again.instruments.last.section, 'end');
    expect(again.energyEnd, 2);
  });

  test('settings fill in whatever the server leaves out', () {
    final settings = SongSettings.fromJson(const {'speed': 0.9});

    expect(settings.speed, 0.9);
    expect(settings.emotion, 0.5);
    expect(settings.instruments.single.name, 'synth pad');
  });

  test("an upload answer is read the way the backend writes it", () {
    final upload = HumUpload.fromJson({
      'status': 'success',
      'filename': 'recording-ab12.wav',
      'melody': [
        {'hz': 60.0, 'start': 0.0, 'duration': 1.0},
        {'hz': 62.0, 'start': 1.0, 'duration': 1.0},
      ],
      'tempo': 97.0,
      'key': 'G',
      'mode': 'major',
      'warnings': ['A little quiet.'],
    });

    expect(upload.filename, 'recording-ab12.wav');
    expect(upload.noteCount, 2);
    expect(upload.warnings, ['A little quiet.']);
  });

  test('notes keep the whole numbers the backend sends as numbers', () {
    final notes = HumNotes.fromJson({
      'sung': [
        {'midi': 60, 'start': 0, 'duration': 0.5},
      ],
      'played': [
        {'midi': 64.2, 'start': 0.5, 'duration': 0.25},
      ],
      'contour': {'step': 0.01, 'segments': []},
    });

    expect(notes.sung.single.midi, 60.0);
    expect(notes.played.single.end, 0.75);
    expect(notes.isEmpty, isFalse);
    expect(const HumNotes().isEmpty, isTrue);
  });
}
