/// Which of the two song makers to use.
enum HumEngine {
  /// A full ensemble arranged around the tune. Best from a clean hum.
  epic('epic', 'Epic'),

  /// Chords and a style around the tune. Steadier on a rough hum.
  simple('simple', 'Simple');

  const HumEngine(this.apiName, this.label);

  final String apiName;
  final String label;
}

/// One instrument in the song. The backend decides these (talk mode adds
/// and removes them); the app keeps them and sends them back.
class Instrument {
  final String name;

  /// `lead` plays the tune and the chords; `background` plays softly underneath.
  final String role;
  final String level;

  /// Where it plays: `all`, `start` (first half) or `end` (second half).
  final String section;

  const Instrument({
    required this.name,
    this.role = 'background',
    this.level = 'soft',
    this.section = 'all',
  });

  factory Instrument.fromJson(Map<String, dynamic> json) => Instrument(
    name: json['name'] as String? ?? '',
    role: json['role'] as String? ?? 'background',
    level: json['level'] as String? ?? 'soft',
    section: json['section'] as String? ?? 'all',
  );

  Map<String, dynamic> toJson() => {
    'name': name,
    'role': role,
    'level': level,
    'section': section,
  };
}

/// How the song should feel. Mirrors the backend's SongSettings
/// (backend/hum/engine/talk/settings.py): three dials from 0 to 1 with 0.5
/// meaning "as hummed", a genre word, the instruments, and how calm or big
/// each half is.
class SongSettings {
  final double emotion;
  final double speed;
  final double pitch;
  final String? style;
  final List<Instrument> instruments;
  final int energyStart;
  final int energyEnd;

  const SongSettings({
    this.emotion = 0.5,
    this.speed = 0.5,
    this.pitch = 0.5,
    this.style = 'cinematic',
    this.instruments = const [
      Instrument(name: 'synth pad', role: 'lead', level: 'normal'),
    ],
    this.energyStart = 0,
    this.energyEnd = 0,
  });

  factory SongSettings.fromJson(Map<String, dynamic> json) {
    final energy = json['energy'] as Map<String, dynamic>? ?? const {};
    final instruments = json['instruments'] as List<dynamic>?;
    return SongSettings(
      emotion: (json['emotion'] as num? ?? 0.5).toDouble(),
      speed: (json['speed'] as num? ?? 0.5).toDouble(),
      pitch: (json['pitch'] as num? ?? 0.5).toDouble(),
      style: json['style'] as String?,
      instruments: instruments == null
          ? const SongSettings().instruments
          : [
              for (final raw in instruments)
                Instrument.fromJson(raw as Map<String, dynamic>),
            ],
      energyStart: (energy['start'] as num? ?? 0).toInt(),
      energyEnd: (energy['end'] as num? ?? 0).toInt(),
    );
  }

  Map<String, dynamic> toJson() => {
    'emotion': emotion,
    'speed': speed,
    'pitch': pitch,
    'style': style,
    'instruments': [for (final part in instruments) part.toJson()],
    'energy': {'start': energyStart, 'end': energyEnd},
  };

  SongSettings copyWith({double? emotion, double? speed, double? pitch}) {
    return SongSettings(
      emotion: emotion ?? this.emotion,
      speed: speed ?? this.speed,
      pitch: pitch ?? this.pitch,
      style: style,
      instruments: instruments,
      energyStart: energyStart,
      energyEnd: energyEnd,
    );
  }
}

/// What the server found in a hum, and the name to send back to refer to it.
class HumUpload {
  final String filename;
  final int noteCount;
  final double tempo;
  final String key;
  final String mode;
  final List<String> warnings;

  const HumUpload({
    required this.filename,
    required this.noteCount,
    required this.tempo,
    required this.key,
    required this.mode,
    this.warnings = const [],
  });

  factory HumUpload.fromJson(Map<String, dynamic> json) => HumUpload(
    filename: json['filename'] as String,
    noteCount: (json['melody'] as List<dynamic>? ?? const []).length,
    tempo: (json['tempo'] as num? ?? 0).toDouble(),
    key: json['key'] as String? ?? '',
    mode: json['mode'] as String? ?? '',
    warnings: [
      for (final warning in json['warnings'] as List<dynamic>? ?? const [])
        warning.toString(),
    ],
  );
}

/// A note: MIDI pitch (60 = middle C), when it starts and how long it lasts,
/// in seconds.
class HumNote {
  final double midi;
  final double start;
  final double duration;

  const HumNote({
    required this.midi,
    required this.start,
    required this.duration,
  });

  factory HumNote.fromJson(Map<String, dynamic> json) => HumNote(
    midi: (json['midi'] as num).toDouble(),
    start: (json['start'] as num).toDouble(),
    duration: (json['duration'] as num).toDouble(),
  );

  double get end => start + duration;
}

/// The notes heard in the hum, and the notes the song plays, for drawing.
class HumNotes {
  final List<HumNote> sung;
  final List<HumNote> played;

  const HumNotes({this.sung = const [], this.played = const []});

  factory HumNotes.fromJson(Map<String, dynamic> json) =>
      HumNotes(sung: _notes(json['sung']), played: _notes(json['played']));

  static List<HumNote> _notes(Object? raw) => [
    for (final note in raw as List<dynamic>? ?? const [])
      HumNote.fromJson(note as Map<String, dynamic>),
  ];

  bool get isEmpty => sung.isEmpty && played.isEmpty;
}

/// The answer to one typed or spoken command.
class TalkTurn {
  final String heard;

  /// `adjust`, `undo`, `off_topic`, `unclear` or `error`.
  final String intent;
  final SongSettings settings;
  final List<String> changed;
  final String reply;
  final String? error;
  final String speechId;

  const TalkTurn({
    required this.heard,
    required this.intent,
    required this.settings,
    required this.changed,
    required this.reply,
    required this.error,
    required this.speechId,
  });

  factory TalkTurn.fromJson(Map<String, dynamic> json) => TalkTurn(
    heard: json['heard'] as String? ?? '',
    intent: json['intent'] as String? ?? 'unclear',
    settings: SongSettings.fromJson(
      json['settings'] as Map<String, dynamic>? ?? const {},
    ),
    changed: [
      for (final name in json['changed'] as List<dynamic>? ?? const [])
        name.toString(),
    ],
    reply: json['reply'] as String? ?? '',
    error: json['error'] as String?,
    speechId: json['speech_id'] as String? ?? '',
  );

  /// Whether the song needs making again.
  bool get changesSong => changed.isNotEmpty;
}
