/// The band engine's song as one editable project. Mirrors
/// backend/hum/song/project.py field for field: the app holds it, the chat
/// and the Studio edit it, and the server renders it. Times are in beats.
library;

class ProjectNote {
  final int pitch;
  final double start;
  final double duration;
  final int velocity;

  const ProjectNote({
    required this.pitch,
    required this.start,
    required this.duration,
    this.velocity = 90,
  });

  double get end => start + duration;

  factory ProjectNote.fromJson(Map<String, dynamic> json) => ProjectNote(
    pitch: (json['pitch'] as num).toInt(),
    start: (json['start'] as num).toDouble(),
    duration: (json['duration'] as num).toDouble(),
    velocity: (json['velocity'] as num? ?? 90).toInt(),
  );

  Map<String, dynamic> toJson() => {
    'pitch': pitch,
    'start': start,
    'duration': duration,
    'velocity': velocity,
  };
}

class TrackEffects {
  final double reverb;
  final double eqLow;
  final double eqHigh;
  final double compression;

  const TrackEffects({
    this.reverb = 0,
    this.eqLow = 0,
    this.eqHigh = 0,
    this.compression = 0,
  });

  factory TrackEffects.fromJson(Map<String, dynamic> json) => TrackEffects(
    reverb: _d(json['reverb']),
    eqLow: _d(json['eq_low']),
    eqHigh: _d(json['eq_high']),
    compression: _d(json['compression']),
  );

  Map<String, dynamic> toJson() => {
    'reverb': reverb,
    'eq_low': eqLow,
    'eq_high': eqHigh,
    'compression': compression,
  };
}

class ProjectTrack {
  final String id;
  final String name;

  /// melody, chords, bass, pad or drums.
  final String role;
  final int program;
  final List<ProjectNote> notes;
  final double volume;
  final double pan;
  final bool mute;
  final bool solo;
  final TrackEffects effects;

  const ProjectTrack({
    required this.id,
    required this.name,
    required this.role,
    required this.program,
    this.notes = const [],
    this.volume = 0.8,
    this.pan = 0,
    this.mute = false,
    this.solo = false,
    this.effects = const TrackEffects(),
  });

  bool get isDrums => role == 'drums';

  factory ProjectTrack.fromJson(Map<String, dynamic> json) => ProjectTrack(
    id: json['id'] as String,
    name: json['name'] as String? ?? json['id'] as String,
    role: json['role'] as String,
    program: (json['program'] as num).toInt(),
    notes: [
      for (final note in json['notes'] as List<dynamic>? ?? const [])
        ProjectNote.fromJson(note as Map<String, dynamic>),
    ],
    volume: _d(json['volume'], 0.8),
    pan: _d(json['pan']),
    mute: json['mute'] as bool? ?? false,
    solo: json['solo'] as bool? ?? false,
    effects: TrackEffects.fromJson(
      json['effects'] as Map<String, dynamic>? ?? const {},
    ),
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'role': role,
    'program': program,
    'notes': [for (final note in notes) note.toJson()],
    'volume': volume,
    'pan': pan,
    'mute': mute,
    'solo': solo,
    'effects': effects.toJson(),
  };
}

class ProjectSection {
  /// intro, verse, chorus or outro.
  final String name;
  final int startBar;
  final int bars;
  final int intensity;
  final int variation;

  const ProjectSection({
    required this.name,
    required this.startBar,
    required this.bars,
    this.intensity = 1,
    this.variation = 0,
  });

  factory ProjectSection.fromJson(Map<String, dynamic> json) => ProjectSection(
    name: json['name'] as String,
    startBar: (json['start_bar'] as num).toInt(),
    bars: (json['bars'] as num).toInt(),
    intensity: (json['intensity'] as num? ?? 1).toInt(),
    variation: (json['variation'] as num? ?? 0).toInt(),
  );

  Map<String, dynamic> toJson() => {
    'name': name,
    'start_bar': startBar,
    'bars': bars,
    'intensity': intensity,
    'variation': variation,
  };
}

class ChordSymbol {
  final int bar;
  final int root;
  final String quality;
  final String degree;

  const ChordSymbol({
    required this.bar,
    required this.root,
    required this.quality,
    required this.degree,
  });

  factory ChordSymbol.fromJson(Map<String, dynamic> json) => ChordSymbol(
    bar: (json['bar'] as num).toInt(),
    root: (json['root'] as num).toInt(),
    quality: json['quality'] as String,
    degree: json['degree'] as String,
  );

  Map<String, dynamic> toJson() => {
    'bar': bar,
    'root': root,
    'quality': quality,
    'degree': degree,
  };
}

class SongProject {
  static const int formatVersion = 1;

  final double tempo;
  final String tonic;
  final String mode;
  final String preset;
  final String mood;
  final double swing;
  final int transpose;
  final double humTempo;
  final double speed;
  final List<int> energy;
  final bool? pad;
  final List<String> removed;
  final List<ProjectNote> phrase;
  final List<ProjectSection> sections;
  final List<ChordSymbol> chords;
  final List<ProjectTrack> tracks;

  /// The upload this came from.
  final String? hum;

  const SongProject({
    required this.tempo,
    required this.tonic,
    required this.mode,
    required this.preset,
    this.mood = 'neutral',
    this.swing = 0.5,
    this.transpose = 0,
    this.humTempo = 0,
    this.speed = 1,
    this.energy = const [0, 0],
    this.pad,
    this.removed = const [],
    this.phrase = const [],
    this.sections = const [],
    this.chords = const [],
    this.tracks = const [],
    this.hum,
  });

  ProjectTrack? track(String role) {
    for (final track in tracks) {
      if (track.role == role) return track;
    }
    return null;
  }

  factory SongProject.fromJson(Map<String, dynamic> json) => SongProject(
    tempo: _d(json['tempo']),
    tonic: json['tonic'] as String,
    mode: json['mode'] as String,
    preset: json['preset'] as String,
    mood: json['mood'] as String? ?? 'neutral',
    swing: _d(json['swing'], 0.5),
    transpose: (json['transpose'] as num? ?? 0).toInt(),
    humTempo: _d(json['hum_tempo']),
    speed: _d(json['speed'], 1),
    energy: [
      for (final e in json['energy'] as List<dynamic>? ?? const [0, 0])
        (e as num).toInt(),
    ],
    pad: json['pad'] as bool?,
    removed: [
      for (final r in json['removed'] as List<dynamic>? ?? const [])
        r as String,
    ],
    phrase: [
      for (final n in json['phrase'] as List<dynamic>? ?? const [])
        ProjectNote.fromJson(n as Map<String, dynamic>),
    ],
    sections: [
      for (final s in json['sections'] as List<dynamic>? ?? const [])
        ProjectSection.fromJson(s as Map<String, dynamic>),
    ],
    chords: [
      for (final c in json['chords'] as List<dynamic>? ?? const [])
        ChordSymbol.fromJson(c as Map<String, dynamic>),
    ],
    tracks: [
      for (final t in json['tracks'] as List<dynamic>? ?? const [])
        ProjectTrack.fromJson(t as Map<String, dynamic>),
    ],
    hum: json['hum'] as String?,
  );

  Map<String, dynamic> toJson() => {
    'version': formatVersion,
    'tempo': tempo,
    'tonic': tonic,
    'mode': mode,
    'preset': preset,
    'mood': mood,
    'swing': swing,
    'transpose': transpose,
    'hum_tempo': humTempo,
    'speed': speed,
    'energy': energy,
    'pad': pad,
    'removed': removed,
    'phrase': [for (final n in phrase) n.toJson()],
    'sections': [for (final s in sections) s.toJson()],
    'chords': [for (final c in chords) c.toJson()],
    'tracks': [for (final t in tracks) t.toJson()],
    'hum': hum,
  };
}

double _d(Object? value, [double fallback = 0]) =>
    (value as num? ?? fallback).toDouble();
