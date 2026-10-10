import 'package:flutter_test/flutter_test.dart';

import 'package:hu_accomponist/integrations/hum/chat_models.dart';
import 'package:hu_accomponist/integrations/hum/song_project.dart';

/// A project as the server sends it (backend/hum/song/project.py to_json).
const Map<String, dynamic> fromServer = {
  'version': 1,
  'tempo': 90.0,
  'tonic': 'D',
  'mode': 'minor',
  'preset': 'lofi',
  'mood': 'chill',
  'swing': 0.6,
  'transpose': 2,
  'hum_tempo': 92.1,
  'speed': 1.05,
  'energy': [1, -1],
  'pad': true,
  'removed': ['drums'],
  'phrase': [
    {'pitch': 50, 'start': 0.0, 'duration': 1.0, 'velocity': 110},
  ],
  'sections': [
    {
      'name': 'intro',
      'start_bar': 0,
      'bars': 2,
      'intensity': 1,
      'variation': 0,
    },
    {
      'name': 'chorus',
      'start_bar': 2,
      'bars': 6,
      'intensity': 2,
      'variation': 3,
    },
  ],
  'chords': [
    {'bar': 0, 'root': 2, 'quality': 'min7', 'degree': 'i'},
  ],
  'tracks': [
    {
      'id': 'melody',
      'name': 'Melody · Vibraphone',
      'role': 'melody',
      'program': 11,
      'notes': [
        {'pitch': 62, 'start': 8.0, 'duration': 1.0, 'velocity': 118},
      ],
      'volume': 1.0,
      'pan': 0.0,
      'mute': false,
      'solo': true,
      'effects': {
        'reverb': 0.3,
        'eq_low': 0.0,
        'eq_high': -2.0,
        'compression': 0.2,
      },
    },
  ],
  'hum': 'hum-1.wav',
};

void main() {
  test('a project from the server goes back exactly as it came', () {
    expect(SongProject.fromJson(fromServer).toJson(), fromServer);
  });

  test('the fields read as they should', () {
    final project = SongProject.fromJson(fromServer);
    expect(project.track('melody')!.effects.eqHigh, -2);
    expect(project.track('melody')!.solo, isTrue);
    expect(project.sections.last.variation, 3);
    expect(project.track('drums'), isNull);
    expect(project.pad, isTrue);
    expect(project.removed, ['drums']);
    expect(project.energy, [1, -1]);
  });

  test('a chat reply carries the edited project, or none', () {
    final edited = ChatReply.fromJson({
      'heard': 'softer drums',
      'intent': 'edit',
      'reply': 'Done.',
      'project': fromServer,
      'changed': ['melody'],
      'label': 'drums quieter',
      'speech_id': 'abc',
    });
    expect(edited.project!.preset, 'lofi');
    expect(edited.changed, ['melody']);
    expect((edited.label, edited.speechId), ('drums quieter', 'abc'));
    final question = ChatReply.fromJson({
      'intent': 'clarify',
      'reply': 'Which part?',
      'project': null,
    });
    expect(question.project, isNull);
  });
}
