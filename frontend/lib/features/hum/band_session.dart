import 'dart:typed_data';

import 'package:hu_accomponist/features/hum/edit_history.dart';
import 'package:hu_accomponist/integrations/hum/hum_models.dart';
import 'package:hu_accomponist/integrations/hum/hum_repository.dart';
import 'package:hu_accomponist/integrations/hum/song_project.dart';

/// The band engine's song for the current hum: the editable project, every
/// version of it (so any edit, from the chat or the controls, can be undone),
/// and making each version audible. No widgets; HumController drives it.
class BandSession {
  BandSession(this._repository);

  final HumRepository _repository;
  EditHistory<SongProject>? _history;
  String? _humFilename;

  SongProject? get project => _history?.current;
  bool get canUndo => _history?.canUndo ?? false;
  bool get canRedo => _history?.canRedo ?? false;
  String? get undoLabel => _history?.undoLabel;
  String? get redoLabel => _history?.redoLabel;

  /// Whether this hum's song is already here (switching back to Band keeps
  /// its edits instead of arranging it again).
  bool holds(HumUpload hum) => _history != null && _humFilename == hum.filename;

  /// Arranges the hum afresh: a new history starts.
  Future<SongProject> arrange(HumUpload hum, SongSettings settings) async {
    final arranged = await _repository.project(hum, settings);
    _history = EditHistory(arranged);
    _humFilename = hum.filename;
    return arranged;
  }

  /// The audio and the notes graph for [version].
  Future<(Uint8List, HumNotes)> render(SongProject version) async {
    final results = await Future.wait<Object>([
      _repository.projectAudio(version),
      _repository.projectNotes(version),
    ]);
    return (results[0] as Uint8List, results[1] as HumNotes);
  }

  void push(SongProject version, String label) =>
      _history?.push(version, label);

  SongProject? undo() => _history?.undo();
  SongProject? redo() => _history?.redo();

  void clear() {
    _history = null;
    _humFilename = null;
  }
}
