import 'dart:typed_data';

import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/integrations/hum/saved_hum_store.dart';
import 'package:hu_accomponist/integrations/hum/song_style.dart';

/// What Save keeps of a song, named for how it sounds: "Lo-fi hum in D
/// minor" (the genre for the band engine, the engine's name otherwise).
SavedHum songToSave({
  required Uint8List song,
  required HumUpload hum,
  required SongSettings settings,
  required HumEngine engine,
  required List<HumNote> sung,
}) {
  final style = engine == HumEngine.band
      ? SongGenre.fromStyle(settings.style)?.label ?? engine.label
      : engine.label;
  return SavedHum(
    id: '',
    title: [
      '$style hum',
      if (hum.key.isNotEmpty) 'in ${hum.key} ${hum.mode}',
    ].join(' '),
    savedAt: DateTime.now(),
    style: style,
    key: hum.key,
    mode: hum.mode,
    tempo: hum.tempo,
    seconds: wavSeconds(song),
    sung: sung,
    engine: engine.apiName,
    humFilename: hum.filename,
    settings: settings,
  );
}
