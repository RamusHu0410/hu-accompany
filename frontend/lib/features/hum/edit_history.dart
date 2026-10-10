/// Versions of something being edited, with a label for each change, so any
/// edit can be undone and redone. Plain Dart: no widgets, no I/O.
class EditHistory<T> {
  EditHistory(T first, {this.limit = 50}) : _versions = [(first, '')];

  /// How many versions are kept; the oldest go first.
  final int limit;
  final List<(T, String)> _versions;
  int _at = 0;

  T get current => _versions[_at].$1;
  bool get canUndo => _at > 0;
  bool get canRedo => _at < _versions.length - 1;

  /// What undo would take back, e.g. "drums quieter".
  String? get undoLabel => canUndo ? _versions[_at].$2 : null;

  /// What redo would bring back.
  String? get redoLabel => canRedo ? _versions[_at + 1].$2 : null;

  /// A new version. Anything that was undone is gone for good.
  void push(T version, String label) {
    _versions
      ..removeRange(_at + 1, _versions.length)
      ..add((version, label));
    if (_versions.length > limit) _versions.removeAt(0);
    _at = _versions.length - 1;
  }

  /// The version before, or null when there's nothing to undo.
  T? undo() {
    if (!canUndo) return null;
    _at--;
    return current;
  }

  /// The version undone last, or null when there's nothing to redo.
  T? redo() {
    if (!canRedo) return null;
    _at++;
    return current;
  }
}
