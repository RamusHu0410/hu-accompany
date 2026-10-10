import 'package:flutter_test/flutter_test.dart';

import 'package:hu_accomponist/integrations/audio/Rust_Session.dart';
import 'package:hu_accomponist/integrations/feedback/Phrase_send2_server.dart';
import 'package:hu_accomponist/src/rust/models.dart';

// `volume` is how loudly Rust heard a note played (0.0 quiet .. 1.0 loud, see
// native_ffi/src/volume.rs). It has to survive the two hops Dart makes:
// Rust -> Dart notes -> the JSON sent to /api/feedback/phrase, and the JSON
// from getUserData() -> Dart notes.
void main() {
  Notes note({double? volume, double? start = 100, double? end = 600}) => Notes(
    noteId: BigInt.from(7),
    pitchHz: 440,
    startTimeMs: start,
    endTimeMs: end,
    durationMs: (start != null && end != null) ? end - start : null,
    isEnd: false,
    volume: volume,
  );

  group('request to the backend', () {
    test('sends the volume when Rust measured one', () {
      final json = PhraseUploadService.userNoteToJson(note(volume: 0.8546));
      expect(json['volume'], closeTo(0.8546, 1e-6));
    });

    test('leaves the key out when there is no volume, as for has_accent', () {
      final json = PhraseUploadService.userNoteToJson(note());
      expect(json.containsKey('volume'), isFalse);
    });

    test('keeps the fields the backend requires', () {
      final json = PhraseUploadService.userNoteToJson(note(volume: 0.5));
      expect(json['note_id'], 7);
      expect(json['pitch_hz'], 440);
      expect(json['start_time_ms'], 100);
      expect(json['end_time_ms'], 600);
      expect(json['duration_ms'], 500);
    });

    test('a note with no timing still gets a volume sent and numbers for the rest', () {
      final json = PhraseUploadService.userNoteToJson(
        note(volume: 0.3, start: null, end: null),
      );
      expect(json['volume'], closeTo(0.3, 1e-6));
      expect(json['start_time_ms'], 0);
    });
  });

  group('notes read back from getUserData()', () {
    final base = <String, dynamic>{
      'note_id': 3,
      'pitch_hz': 261.6,
      'start_time_ms': 10.0,
      'end_time_ms': 410.0,
      'duration_ms': 400.0,
      'is_end': true,
    };

    test('keeps the volume', () {
      final parsed = RustSession.notesFromJson({...base, 'volume': 0.42});
      expect(parsed.volume, closeTo(0.42, 1e-6));
    });

    test('accepts a whole-number volume', () {
      expect(RustSession.notesFromJson({...base, 'volume': 1}).volume, 1.0);
    });

    test('a missing or null volume is null, not zero', () {
      expect(RustSession.notesFromJson(base).volume, isNull);
      expect(RustSession.notesFromJson({...base, 'volume': null}).volume, isNull);
    });
  });
}
