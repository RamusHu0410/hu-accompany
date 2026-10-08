import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:path_provider/path_provider.dart';

import 'package:hu_accomponist/integrations/hum/hum_models.dart';

/// A hummed song the user saved: the song as it sounded when they tapped
/// Save, and enough about it to list it on the shelf.
class SavedHum {
  final String id;
  final String title;
  final DateTime savedAt;

  /// The engine's label, or the genre's for the band engine ("Lo-fi").
  final String style;
  final String key;
  final String mode;
  final double tempo;
  final double seconds;

  /// The notes hummed, for drawing the card.
  final List<HumNote> sung;

  /// What made it, so it can be made again or opened for editing later.
  final String engine;
  final String humFilename;
  final SongSettings settings;

  const SavedHum({
    required this.id,
    required this.title,
    required this.savedAt,
    required this.style,
    required this.key,
    required this.mode,
    required this.tempo,
    required this.seconds,
    required this.sung,
    required this.engine,
    required this.humFilename,
    required this.settings,
  });

  String get audioFile => '$id.wav';

  SavedHum renamed(String title) => SavedHum(
    id: id,
    title: title,
    savedAt: savedAt,
    style: style,
    key: key,
    mode: mode,
    tempo: tempo,
    seconds: seconds,
    sung: sung,
    engine: engine,
    humFilename: humFilename,
    settings: settings,
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'title': title,
    'savedAt': savedAt.toIso8601String(),
    'style': style,
    'key': key,
    'mode': mode,
    'tempo': tempo,
    'seconds': seconds,
    'sung': [for (final note in sung) note.toJson()],
    'engine': engine,
    'humFilename': humFilename,
    'settings': settings.toJson(),
  };

  factory SavedHum.fromJson(Map<String, dynamic> json) => SavedHum(
    id: json['id'] as String,
    title: json['title'] as String? ?? 'Hummed song',
    savedAt:
        DateTime.tryParse(json['savedAt'] as String? ?? '') ?? DateTime.now(),
    style: json['style'] as String? ?? '',
    key: json['key'] as String? ?? '',
    mode: json['mode'] as String? ?? '',
    tempo: (json['tempo'] as num? ?? 0).toDouble(),
    seconds: (json['seconds'] as num? ?? 0).toDouble(),
    sung: [
      for (final note in json['sung'] as List<dynamic>? ?? const [])
        HumNote.fromJson(note as Map<String, dynamic>),
    ],
    engine: json['engine'] as String? ?? '',
    humFilename: json['humFilename'] as String? ?? '',
    settings: SongSettings.fromJson(
      json['settings'] as Map<String, dynamic>? ?? const {},
    ),
  );
}

/// The hummed songs kept on this device. An interface so tests and the
/// controllers don't need a file system.
abstract class SavedHumStore {
  /// Every saved song, newest first.
  Future<List<SavedHum>> loadAll();

  /// Keeps [wav] with [details] (whose id is replaced by a fresh one) and
  /// returns what was saved.
  Future<SavedHum> save(Uint8List wav, SavedHum details);

  Future<void> rename(String id, String title);

  Future<void> delete(String id);

  /// Where a saved song's audio is, to play it.
  Future<File> audioFor(SavedHum song);
}

/// Saved songs as files: `<id>.wav` beside an `index.json` listing them, in
/// a folder of the app's documents (kept, and backed up, by the system).
class FileSavedHumStore implements SavedHumStore {
  FileSavedHumStore({Future<Directory> Function()? folder})
    : _folder = folder ?? _documentsFolder;

  final Future<Directory> Function() _folder;

  static Future<Directory> _documentsFolder() async => Directory(
    '${(await getApplicationDocumentsDirectory()).path}/hummed_songs',
  );

  Future<Directory> _ready() async => (await _folder()).create(recursive: true);

  @override
  Future<List<SavedHum>> loadAll() async {
    final index = File('${(await _ready()).path}/index.json');
    if (!await index.exists()) return [];
    try {
      final decoded = jsonDecode(await index.readAsString()) as List<dynamic>;
      return [
        for (final entry in decoded)
          SavedHum.fromJson(entry as Map<String, dynamic>),
      ];
    } on FormatException {
      return []; // a damaged index shouldn't break the shelf
    } on TypeError {
      return [];
    }
  }

  @override
  Future<SavedHum> save(Uint8List wav, SavedHum details) async {
    final folder = await _ready();
    final id = DateTime.now().microsecondsSinceEpoch.toRadixString(36);
    final saved = SavedHum.fromJson({...details.toJson(), 'id': id});
    await File(
      '${folder.path}/${saved.audioFile}',
    ).writeAsBytes(wav, flush: true);
    await _write([saved, ...await loadAll()]);
    return saved;
  }

  @override
  Future<void> rename(String id, String title) async {
    await _write([
      for (final song in await loadAll())
        song.id == id ? song.renamed(title) : song,
    ]);
  }

  @override
  Future<void> delete(String id) async {
    final songs = await loadAll();
    final gone = songs.where((song) => song.id == id).toList();
    await _write(songs.where((song) => song.id != id).toList());
    for (final song in gone) {
      final audio = await audioFor(song);
      if (await audio.exists()) await audio.delete();
    }
  }

  @override
  Future<File> audioFor(SavedHum song) async =>
      File('${(await _ready()).path}/${song.audioFile}');

  /// Written beside the index first, then moved over it, so a crash halfway
  /// never leaves a half-written index.
  Future<void> _write(List<SavedHum> songs) async {
    final folder = await _ready();
    final next = File('${folder.path}/index.json.next');
    await next.writeAsString(
      jsonEncode([for (final song in songs) song.toJson()]),
      flush: true,
    );
    await next.rename('${folder.path}/index.json');
  }
}

/// How long a 16-bit PCM WAV plays, from its header; 0 when it isn't one.
double wavSeconds(Uint8List wav) {
  if (wav.length < 44 || String.fromCharCodes(wav.sublist(0, 4)) != 'RIFF') {
    return 0;
  }
  final header = ByteData.sublistView(wav);
  final channels = header.getUint16(22, Endian.little);
  final rate = header.getUint32(24, Endian.little);
  final bits = header.getUint16(34, Endian.little);
  final bytesPerSecond = rate * channels * bits ~/ 8;
  if (bytesPerSecond == 0) return 0;
  return (wav.length - 44) / bytesPerSecond;
}
