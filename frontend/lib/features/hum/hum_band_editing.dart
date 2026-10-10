part of 'hum_controller.dart';

/// The band engine's editing, mixed into [HumController]: genre and mood on
/// the song itself, undo and redo, and the chat's host (it asks for the song,
/// switching to Band first if needed, and hands back edits). Every edit is a
/// step in [BandSession]'s history.
mixin _BandEditing on ChangeNotifier implements ChatHost {
  // What HumController provides.
  BandSession get band;
  ChatController get chat;
  HumRepository get _repository;
  HumEngine get engine;
  set engine(HumEngine value);
  SongSettings get settings;
  set settings(SongSettings value);
  HumUpload? get hum;
  HumPhase get phase;
  set phase(HumPhase value);
  String? get error;
  set error(String? value);
  set notice(String? value);
  bool get isBusy;
  int get _job;
  set _job(int value);
  Future<void> _remakeIfHummed();
  void _shown(
    Uint8List audio,
    HumNotes graph,
    (SongSettings, HumEngine) madeWith,
  );
  void _fail(int job, String message);
  void _changed();

  bool get _editingBand => engine == HumEngine.band && band.project != null;

  @override
  bool get canUndo => engine == HumEngine.band && band.canUndo;
  @override
  bool get canRedo => engine == HumEngine.band && band.canRedo;

  /// The band engine's genre: the song's own once there is one.
  SongGenre? get genre =>
      SongGenre.fromStyle(_editingBand ? band.project!.preset : settings.style);

  /// The band engine's mood; null is "as hummed".
  SongMood? get mood =>
      SongMood.fromName(_editingBand ? band.project!.mood : settings.mood);

  Future<void> setGenre(SongGenre next) async {
    if (next == genre) return;
    settings = settings.withStyle(next.apiName);
    if (_editingBand) return _editBand([ProjectEdits.genre(next.apiName)]);
    _changed();
    await _remakeIfHummed();
  }

  /// Picking the mood that's already chosen goes back to "as hummed".
  Future<void> setMood(SongMood? next) async {
    final target = next == mood ? null : next;
    settings = settings.withMood(target?.apiName);
    if (_editingBand) {
      return _editBand([ProjectEdits.mood(target?.apiName ?? 'neutral')]);
    }
    _changed();
    await _remakeIfHummed();
  }

  // ── Undo and redo (Band) ─────────────────────────────────────────────

  Future<void> undo() async => _step(band.undo, band.redo, play: true);
  Future<void> redo() async => _step(band.redo, band.undo, play: true);
  String? get undoLabel => canUndo ? band.undoLabel : null;
  String? get redoLabel => canRedo ? band.redoLabel : null;

  @override
  Future<bool> undoEdit() => _step(band.undo, band.redo, play: false);
  @override
  Future<bool> redoEdit() => _step(band.redo, band.undo, play: false);

  Future<bool> _step(
    SongProject? Function() move,
    SongProject? Function() back, {
    required bool play,
  }) async {
    if (engine != HumEngine.band || isBusy) return false;
    final version = move();
    if (version == null) return false;
    final done = await _bandJob((job) => _showBand(job, version, play: play));
    if (!done) back(); // the song didn't change, so neither does the history
    return done;
  }

  // ── The chat's host ──────────────────────────────────────────────────

  String _notReady = '';

  @override
  String get notReadyReason => _notReady;

  @override
  Future<SongProject?> projectForChat() async {
    final current = hum;
    if (current == null ||
        phase == HumPhase.recording ||
        phase == HumPhase.analyzing) {
      _notReady = 'Hum a tune first, then tell me how to change it.';
      return null;
    }
    if (engine != HumEngine.band) {
      engine = HumEngine.band;
      notice = EngineNotices.switchedForChat;
      chat.addNotice(EngineNotices.switchedForChat);
      await _bandJob((job) => _makeBand(job, current, play: false));
    } else if (phase == HumPhase.making) {
      _notReady = "I'm still making the song. Try again in a moment.";
      return null;
    }
    _notReady = error ?? "The song isn't ready yet.";
    return band.holds(current) ? band.project : null;
  }

  @override
  Future<void> applyChatEdit(SongProject project, String label) async {
    final done = await _bandJob(
      (job) => _showBand(job, project, play: false, label: label),
    );
    if (!done) throw Exception(error ?? 'the song could not be made');
  }

  /// The band song for [current]: the one being edited if there is one (so
  /// coming back to Band keeps its edits), else a new arrangement.
  Future<void> _makeBand(
    int job,
    HumUpload current, {
    required bool play,
  }) async {
    final project = band.holds(current)
        ? band.project!
        : await band.arrange(current, settings);
    if (job != _job) return;
    await _showBand(job, project, play: play);
  }

  /// Renders [project] and makes it the song; with a [label], it's also a
  /// new step in the history.
  Future<void> _showBand(
    int job,
    SongProject project, {
    required bool play,
    String? label,
  }) async {
    final (audio, graph) = await band.render(project);
    if (job != _job) return;
    if (label != null) band.push(project, label);
    final madeWith = settings
        .withStyle(project.preset)
        .withMood(project.mood == 'neutral' ? null : project.mood);
    _shown(audio, graph, (madeWith, HumEngine.band));
    if (play) await playSong();
  }

  Future<void> _editBand(List<Map<String, dynamic>> edits) async {
    final project = band.project;
    if (project == null) return;
    await _bandJob((job) async {
      final result = await _repository.editProject(project, edits);
      if (!result.changedAnything) {
        phase = HumPhase.idle;
        error = result.refused.isEmpty ? null : result.refused.first;
        return _changed();
      }
      await _showBand(job, result.project, play: true, label: result.label);
    });
  }

  /// Runs band work as the current job. False when it failed.
  Future<bool> _bandJob(Future<void> Function(int job) work) async {
    final job = ++_job;
    phase = HumPhase.making;
    error = null;
    _changed();
    try {
      await work(job);
      return job == _job && error == null;
    } on ApiException catch (e) {
      _fail(job, e.message);
    } on Exception catch (e) {
      _fail(job, "Couldn't make the song ($e).");
    }
    return false;
  }
}
