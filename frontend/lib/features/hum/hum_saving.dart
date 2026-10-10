part of 'hum_controller.dart';

/// Save, mixed into [HumController]: keeps the song as it sounds now on the
/// shelf (see saved_hum_store.dart), named for its style and key.
mixin _Saving on ChangeNotifier {
  // What HumController provides.
  SavedHumStore get _store;
  Uint8List? get _song;
  (SongSettings, HumEngine)? get _songMadeWith;
  HumUpload? get hum;
  HumNotes get notes;
  HumPhase get phase;
  set error(String? value);
  void _changed();

  bool saving = false;

  /// Whether the song as it is now is already on the shelf. Making a new
  /// version of the song sets it back to false.
  bool savedThisSong = false;

  bool get canSave =>
      _song != null && phase == HumPhase.idle && !saving && !savedThisSong;

  /// Saves the song as it is now to the shelf, named for its style and key.
  /// True when it was saved.
  Future<bool> save() async {
    final song = _song, current = hum, madeWith = _songMadeWith;
    if (!canSave || song == null || current == null || madeWith == null) {
      return false;
    }
    saving = true;
    _changed();
    try {
      final (madeSettings, madeEngine) = madeWith;
      await _store.save(
        song,
        songToSave(
          song: song,
          hum: current,
          settings: madeSettings,
          engine: madeEngine,
          sung: notes.sung,
        ),
      );
      savedThisSong = true;
      return true;
    } on Exception catch (e) {
      error = "Couldn't save the song ($e).";
      return false;
    } finally {
      saving = false;
      _changed();
    }
  }
}
