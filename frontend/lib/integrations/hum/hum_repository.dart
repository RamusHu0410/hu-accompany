import 'dart:convert';
import 'dart:typed_data';

import 'package:hu_accomponist/integrations/hum/chat_models.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/integrations/hum/song_project.dart';
import 'package:hu_accomponist/integrations/server/api_client.dart';

/// The hum feature's calls to the backend (backend/hum/README.md).
///
/// An interface so the controller can be tested without a server.
abstract class HumRepository {
  /// Sends a recording; the server finds the tune in it.
  Future<HumUpload> upload(String wavPath);

  /// The song made from a saved hum, as WAV bytes.
  Future<Uint8List> song(
    HumUpload hum,
    SongSettings settings,
    HumEngine engine,
  );

  /// The notes heard and the notes the song plays, for drawing.
  Future<HumNotes> notes(
    HumUpload hum,
    SongSettings settings,
    HumEngine engine,
  );

  /// The hum arranged by the band engine, as an editable project.
  Future<SongProject> project(HumUpload hum, SongSettings settings);

  /// A project mixed as WAV bytes. Only parts that changed are rendered again.
  Future<Uint8List> projectAudio(SongProject project);

  /// The hum and the project's melody, for the notes graph.
  Future<HumNotes> projectNotes(SongProject project);

  /// Edits made by the app's own controls (no chat), e.g. a new genre.
  Future<EditResult> editProject(
    SongProject project,
    List<Map<String, dynamic>> edits,
  );

  /// One typed chat message, and what it did to the song.
  Future<ChatReply> chat(
    String text,
    SongProject project, {
    required bool canUndo,
    required bool canRedo,
  });

  /// One spoken chat message (a WAV recording).
  Future<ChatReply> chatVoice(
    String wavPath,
    SongProject project, {
    required bool canUndo,
    required bool canRedo,
  });

  /// Where a chat reply's speech (MP3) can be streamed from.
  Future<Uri> chatSpeechUrl(String speechId);

  /// The hum exactly as hummed, with no quantizing or arrangement.
  Future<RawHum> raw(HumUpload hum);

  /// Those raw notes played on [instrument], as WAV bytes.
  Future<Uint8List> rawAudio(HumUpload hum, RawInstrument instrument);

  /// Those raw notes as a standard MIDI file.
  Future<Uint8List> rawMidi(HumUpload hum);
}

class ServerHumRepository implements HumRepository {
  const ServerHumRepository({
    this.client = const ApiClient(),
    // Making a song takes seconds, but a slow machine shouldn't read as a failure.
    this.songTimeout = const Duration(seconds: 90),
  });

  final ApiClient client;
  final Duration songTimeout;

  @override
  Future<HumUpload> upload(String wavPath) async {
    final response = ApiClient.ensureOk(
      await client.postFile(
        '/api/hum/upload',
        field: 'file',
        filePath: wavPath,
      ),
    );
    return HumUpload.fromJson(_json(response.bodyBytes));
  }

  @override
  Future<Uint8List> song(
    HumUpload hum,
    SongSettings settings,
    HumEngine engine,
  ) async {
    final response = ApiClient.ensureOk(
      await client.postJson(
        '/api/hum/song',
        _body(hum, settings, engine),
        timeout: songTimeout,
      ),
    );
    return response.bodyBytes;
  }

  @override
  Future<HumNotes> notes(
    HumUpload hum,
    SongSettings settings,
    HumEngine engine,
  ) async {
    final response = ApiClient.ensureOk(
      await client.postJson('/api/hum/notes', _body(hum, settings, engine)),
    );
    return HumNotes.fromJson(_json(response.bodyBytes));
  }

  @override
  Future<SongProject> project(HumUpload hum, SongSettings settings) async {
    final response = ApiClient.ensureOk(
      await client.postJson('/api/hum/project', {
        'hum': hum.filename,
        'settings': settings.toJson(),
      }, timeout: songTimeout),
    );
    return SongProject.fromJson(
      _json(response.bodyBytes)['project'] as Map<String, dynamic>,
    );
  }

  @override
  Future<Uint8List> projectAudio(SongProject project) async {
    final response = ApiClient.ensureOk(
      await client.postJson('/api/hum/project/audio', {
        'project': project.toJson(),
      }, timeout: songTimeout),
    );
    return response.bodyBytes;
  }

  @override
  Future<HumNotes> projectNotes(SongProject project) async {
    final response = ApiClient.ensureOk(
      await client.postJson('/api/hum/project/notes', {
        'project': project.toJson(),
      }),
    );
    return HumNotes.fromJson(_json(response.bodyBytes));
  }

  @override
  Future<EditResult> editProject(
    SongProject project,
    List<Map<String, dynamic>> edits,
  ) async {
    final response = ApiClient.ensureOk(
      await client.postJson('/api/hum/project/edit', {
        'project': project.toJson(),
        'edits': edits,
      }, timeout: songTimeout),
    );
    return EditResult.fromJson(_json(response.bodyBytes));
  }

  @override
  Future<ChatReply> chat(
    String text,
    SongProject project, {
    required bool canUndo,
    required bool canRedo,
  }) async {
    final response = ApiClient.ensureOk(
      await client.postJson('/api/hum/chat', {
        'text': text,
        'project': project.toJson(),
        'can_undo': canUndo,
        'can_redo': canRedo,
      }, timeout: songTimeout),
    );
    return ChatReply.fromJson(_json(response.bodyBytes));
  }

  @override
  Future<ChatReply> chatVoice(
    String wavPath,
    SongProject project, {
    required bool canUndo,
    required bool canRedo,
  }) async {
    final response = ApiClient.ensureOk(
      await client.postFile(
        '/api/hum/chat',
        field: 'audio',
        filePath: wavPath,
        fields: {
          'state': jsonEncode({
            'project': project.toJson(),
            'can_undo': canUndo,
            'can_redo': canRedo,
          }),
        },
      ),
    );
    return ChatReply.fromJson(_json(response.bodyBytes));
  }

  @override
  Future<Uri> chatSpeechUrl(String speechId) =>
      client.resolve('/api/hum/chat/speech/$speechId');

  @override
  Future<RawHum> raw(HumUpload hum) async {
    final response = ApiClient.ensureOk(
      await client.postJson('/api/hum/raw', {'hum': hum.filename}),
    );
    return RawHum.fromJson(_json(response.bodyBytes));
  }

  @override
  Future<Uint8List> rawAudio(HumUpload hum, RawInstrument instrument) async {
    final response = ApiClient.ensureOk(
      await client.postJson('/api/hum/raw/audio', {
        'hum': hum.filename,
        'instrument': instrument.apiName,
      }),
    );
    return response.bodyBytes;
  }

  @override
  Future<Uint8List> rawMidi(HumUpload hum) async {
    final response = ApiClient.ensureOk(
      await client.postJson('/api/hum/raw/midi', {'hum': hum.filename}),
    );
    return response.bodyBytes;
  }

  Map<String, dynamic> _body(
    HumUpload hum,
    SongSettings settings,
    HumEngine engine,
  ) => {
    'hum': hum.filename,
    'settings': settings.toJson(),
    'engine': engine.apiName,
  };

  Map<String, dynamic> _json(Uint8List bytes) =>
      jsonDecode(utf8.decode(bytes)) as Map<String, dynamic>;
}
