import 'package:flutter_test/flutter_test.dart';

import 'package:hu_accomponist/features/hum/edit_history.dart';

void main() {
  test('undo and redo walk the versions, with their labels', () {
    final history = EditHistory('first')
      ..push('second', 'louder')
      ..push('third', 'jazz');

    expect(
      (history.current, history.undoLabel, history.canRedo),
      ('third', 'jazz', false),
    );
    expect(history.undo(), 'second');
    expect((history.undoLabel, history.redoLabel), ('louder', 'jazz'));
    expect(history.undo(), 'first');
    expect(history.undo(), isNull);
    expect(history.redo(), 'second');
    expect(history.redo(), 'third');
    expect(history.redo(), isNull);
  });

  test('a new edit after undoing drops what was undone', () {
    final history = EditHistory(1)
      ..push(2, 'b')
      ..push(3, 'c');
    history.undo();
    history.push(4, 'd');
    expect(history.canRedo, isFalse);
    expect(history.undo(), 2);
  });

  test('only the newest versions are kept', () {
    final history = EditHistory(0, limit: 3);
    for (var i = 1; i <= 5; i++) {
      history.push(i, 'v$i');
    }
    expect(history.undo(), 4);
    expect(history.undo(), 3);
    expect(history.undo(), isNull);
  });
}
