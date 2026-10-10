import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'dart:ui';

import 'package:hu_accomponist/features/hum/file_sharer.dart';
import 'package:hu_accomponist/features/hum/hum_audio.dart';
import 'package:hu_accomponist/integrations/hum/chat_models.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/integrations/hum/hum_repository.dart';
import 'package:hu_accomponist/integrations/hum/saved_hum_store.dart';
import 'package:hu_accomponist/integrations/hum/song_project.dart';
import 'package:hu_accomponist/integrations/server/api_client.dart';

class FakeRecorder implements HumRecorder {
  FakeRecorder({this.allowed = true, this.path = '/tmp/hum.wav'});

  bool allowed;
  String? path;
  int starts = 0;
  bool disposed = false;

  @override
  Future<bool> requestPermission() async => allowed;

  @override
  Future<void> start() async => starts++;

  @override
  Future<String?> stop() async => path;

  @override
  Future<void> dispose() async => disposed = true;
}

class FakePlayer implements SongPlayer {
  final StreamController<bool> _playing = StreamController<bool>.broadcast();
  final StreamController<Duration> _position =
      StreamController<Duration>.broadcast();

  @override
  Stream<Duration> get position => _position.stream;

  /// Moves the playhead, as the real player does while playing.
  void emitPosition(Duration at) => _position.add(at);
  final List<Uint8List> played = [];
  int stops = 0;

  @override
  Stream<bool> get playing => _playing.stream;

  @override
  Future<void> playWav(Uint8List bytes) async {
    played.add(bytes);
    _playing.add(true);
  }

  @override
  Future<void> playUrl(Uri url) async {
    urls.add(url);
    if (urlError != null) throw urlError!;
    _playing.add(true);
  }

  /// When set, playing a URL fails (the voice service is down).
  Object? urlError;

  final List<Uri> urls = [];

  /// The sound ends by itself, as a song or a spoken reply does.
  void finish() => _playing.add(false);

  @override
  Future<void> stop() async {
    stops++;
    _playing.add(false);
  }

  @override
  Future<void> dispose() async {
    await _playing.close();
    await _position.close();
  }
}

class FakeSharer implements FileSharer {
  final List<(String, String, int)> shared = [];

  @override
  Future<void> share(
    Uint8List bytes, {
    required String filename,
    required String mimeType,
    Rect? origin,
  }) async => shared.add((filename, mimeType, bytes.length));
}

/// A server that answers instantly unless a test holds a call back.
class FakeHumRepository implements HumRepository {
  Object? uploadError;

  /// When set, `song` waits for this before answering.
  Completer<void>? songGate;

  final List<(HumEngine, SongSettings)> songCalls = [];
  int uploads = 0;
  int songNumber = 0;

  @override
  Future<HumUpload> upload(String wavPath) async {
    uploads++;
    if (uploadError != null) throw uploadError!;
    return const HumUpload(
      filename: 'hum-1.wav',
      noteCount: 9,
      tempo: 97,
      key: 'G',
      mode: 'major',
    );
  }

  @override
  Future<Uint8List> song(
    HumUpload hum,
    SongSettings settings,
    HumEngine engine,
  ) async {
    songCalls.add((engine, settings));
    final number = ++songNumber;
    await songGate?.future;
    return Uint8List.fromList([number]);
  }

  @override
  Future<HumNotes> notes(
    HumUpload hum,
    SongSettings settings,
    HumEngine engine,
  ) async {
    // The engine decides how many notes the song plays, so tests can tell
    // which request a result came from.
    final played = engine == HumEngine.epic ? 24 : 1;
    return HumNotes(
      sung: const [HumNote(midi: 60, start: 0, duration: 0.5)],
      played: [
        for (var i = 0; i < played; i++)
          HumNote(midi: 60, start: i * 0.1, duration: 0.1),
      ],
    );
  }

  Object? rawError;
  final List<RawInstrument> rawAudioCalls = [];
  int rawCalls = 0;

  static const RawHum rawHum = RawHum(
    notes: [
      HumNote(midi: 50, start: 0, duration: 0.6, velocity: 100),
      HumNote(midi: 52, start: 0.6, duration: 0.6, velocity: 80),
      HumNote(midi: 53, start: 1.2, duration: 1.0, velocity: 110),
    ],
    tempo: 92,
    key: 'D',
    mode: 'minor',
    duration: 2.2,
  );

  @override
  Future<RawHum> raw(HumUpload hum) async {
    rawCalls++;
    if (rawError != null) throw rawError!;
    return rawHum;
  }

  @override
  Future<Uint8List> rawAudio(HumUpload hum, RawInstrument instrument) async {
    rawAudioCalls.add(instrument);
    return Uint8List.fromList([100 + instrument.index]);
  }

  @override
  Future<Uint8List> rawMidi(HumUpload hum) async =>
      Uint8List.fromList('MThd'.codeUnits);

  // ── The band song and the chat ──────────────────────────────────────

  final List<SongSettings> projectCalls = [];
  final List<SongProject> renders = [];
  final List<List<Map<String, dynamic>>> editCalls = [];
  final List<String> chatTexts = [];
  final List<String> chatVoicePaths = [];
  Object? chatError;
  Object? renderError;

  /// Answers a chat message; the default understands "softer drums", "undo"
  /// and "redo", and says it didn't understand anything else.
  ChatReply Function(String text, SongProject project)? onChat;

  /// What the band engine arranges a hum into.
  static SongProject arranged(SongSettings settings) => SongProject(
    tempo: 92,
    tonic: 'G',
    mode: 'major',
    preset: settings.style ?? 'pop',
    mood: settings.mood ?? 'neutral',
    hum: 'hum-1.wav',
    sections: const [
      ProjectSection(name: 'verse', startBar: 0, bars: 4),
      ProjectSection(name: 'chorus', startBar: 4, bars: 4, intensity: 2),
    ],
    tracks: const [
      ProjectTrack(
        id: 'melody',
        name: 'Melody',
        role: 'melody',
        program: 81,
        volume: 1,
      ),
      ProjectTrack(
        id: 'chords',
        name: 'Chords',
        role: 'chords',
        program: 0,
        volume: 0.55,
      ),
      ProjectTrack(
        id: 'drums',
        name: 'Drums',
        role: 'drums',
        program: 0,
        volume: 0.6,
      ),
    ],
  );

  static SongProject withDrums(SongProject p, double volume) => SongProject(
    tempo: p.tempo,
    tonic: p.tonic,
    mode: p.mode,
    preset: p.preset,
    mood: p.mood,
    hum: p.hum,
    sections: p.sections,
    tracks: [
      for (final t in p.tracks)
        t.role == 'drums'
            ? ProjectTrack(
                id: t.id,
                name: t.name,
                role: t.role,
                program: t.program,
                volume: volume,
              )
            : t,
    ],
  );

  static ChatReply understand(String text, SongProject project) {
    final words = text.toLowerCase();
    if (words.contains('drums')) {
      final drums = project.track('drums')!.volume;
      return ChatReply(
        heard: text,
        intent: 'edit',
        reply: 'Drums are softer now.',
        project: withDrums(
          project,
          double.parse((drums - 0.2).toStringAsFixed(2)),
        ),
        changed: const [],
        label: 'drums quieter',
        speechId: 's-${drums.toStringAsFixed(2)}',
      );
    }
    for (final intent in ['undo', 'redo']) {
      if (words.contains(intent)) {
        return ChatReply(
          heard: text,
          intent: intent,
          reply: 'Okay.',
          speechId: 's-$intent',
        );
      }
    }
    return ChatReply(
      heard: text,
      intent: 'unclear',
      reply: 'Say that another way?',
      speechId: 's-unclear',
    );
  }

  @override
  Future<SongProject> project(HumUpload hum, SongSettings settings) async {
    projectCalls.add(settings);
    await songGate?.future;
    return arranged(settings);
  }

  @override
  Future<Uint8List> projectAudio(SongProject project) async {
    renders.add(project);
    if (renderError != null) throw renderError!;
    // a different song for each version: the drums' volume is in it
    return Uint8List.fromList([
      200,
      (project.track('drums')?.volume ?? 0) * 100 ~/ 1,
    ]);
  }

  @override
  Future<HumNotes> projectNotes(SongProject project) async => const HumNotes(
    sung: [HumNote(midi: 60, start: 0, duration: 0.5)],
    played: [
      HumNote(midi: 72, start: 0, duration: 0.5),
      HumNote(midi: 74, start: 0.5, duration: 0.5),
      HumNote(midi: 76, start: 1, duration: 0.5),
    ],
  );

  @override
  Future<EditResult> editProject(
    SongProject project,
    List<Map<String, dynamic>> edits,
  ) async {
    editCalls.add(edits);
    final edit = edits.single;
    final edited = SongProject(
      tempo: project.tempo,
      tonic: project.tonic,
      mode: project.mode,
      preset: edit['genre'] as String? ?? project.preset,
      mood: edit['mood'] as String? ?? project.mood,
      hum: project.hum,
      sections: project.sections,
      tracks: project.tracks,
    );
    return EditResult(
      project: edited,
      label: '${edit['genre'] ?? edit['mood']} now',
    );
  }

  @override
  Future<ChatReply> chat(
    String text,
    SongProject project, {
    required bool canUndo,
    required bool canRedo,
  }) async {
    chatTexts.add(text);
    if (chatError != null) throw chatError!;
    return (onChat ?? understand)(text, project);
  }

  @override
  Future<ChatReply> chatVoice(
    String wavPath,
    SongProject project, {
    required bool canUndo,
    required bool canRedo,
  }) async {
    chatVoicePaths.add(wavPath);
    if (chatError != null) throw chatError!;
    return (onChat ?? understand)('softer drums', project);
  }

  @override
  Future<Uri> chatSpeechUrl(String speechId) async =>
      Uri.parse('http://test/chat/speech/$speechId');
}

const ApiException silentHum = ApiException(
  "I couldn't hear anything. Hum a little louder.",
  code: 'silent',
  status: 400,
);

/// Saved songs in a list, their audio in a temporary folder (written
/// synchronously, so widget tests don't wait on real file I/O).
class MemorySavedHumStore implements SavedHumStore {
  final List<SavedHum> songs = [];
  final Directory folder = Directory.systemTemp.createTempSync('hummed-');
  bool fail = false;
  int _next = 0;

  @override
  Future<List<SavedHum>> loadAll() async => List.of(songs);

  @override
  Future<SavedHum> save(Uint8List wav, SavedHum details) async {
    if (fail) throw const FileSystemException('The disk is full');
    final saved = SavedHum.fromJson({...details.toJson(), 'id': 's${_next++}'});
    File('${folder.path}/${saved.audioFile}').writeAsBytesSync(wav);
    songs.insert(0, saved);
    return saved;
  }

  @override
  Future<void> rename(String id, String title) async {
    final i = songs.indexWhere((song) => song.id == id);
    if (i >= 0) songs[i] = songs[i].renamed(title);
  }

  @override
  Future<void> delete(String id) async => songs.removeWhere((s) => s.id == id);

  @override
  Future<File> audioFor(SavedHum song) async =>
      File('${folder.path}/${song.audioFile}');
}
