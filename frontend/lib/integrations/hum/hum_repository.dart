import 'dart:convert';
import 'dart:typed_data';

import 'package:hu_accomponist/integrations/hum/hum_models.dart';
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

  /// One typed command, and what it did to the settings.
  Future<TalkTurn> talk(
    String text,
    SongSettings settings, {
    SongSettings? previous,
  });

  /// Where a reply's speech (MP3) can be streamed from.
  Future<Uri> speechUrl(String speechId);

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
  Future<TalkTurn> talk(
    String text,
    SongSettings settings, {
    SongSettings? previous,
  }) async {
    final response = ApiClient.ensureOk(
      await client.postJson('/api/hum/talk', {
        'text': text,
        'settings': settings.toJson(),
        if (previous != null) 'previous': previous.toJson(),
      }),
    );
    return TalkTurn.fromJson(_json(response.bodyBytes));
  }

  @override
  Future<Uri> speechUrl(String speechId) =>
      client.resolve('/api/hum/talk/speech/$speechId');

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
