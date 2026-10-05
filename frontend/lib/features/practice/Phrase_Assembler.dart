import 'dart:math' as math;

import 'package:hu_accomponist/features/practice/Exercise.dart';
import 'package:hu_accomponist/src/rust/models.dart';

/// One bar, ready to send to `/api/feedback/phrase`.
class AssembledPhrase {
  /// 1-based bar number, used as the backend's phrase number.
  final int number;

  /// What Rust heard in this bar, one entry per note (see [PhraseAssembler]).
  final List<Notes> userNotes;

  /// Every written note of this bar, in the backend's required shape.
  /// Includes notes that were never heard, which is what lets the backend
  /// report them as missed.
  final List<Map<String, dynamic>> expectedNotes;

  const AssembledPhrase({
    required this.number,
    required this.userNotes,
    required this.expectedNotes,
  });
}

/// Groups what Rust reports into bars.
///
/// Rust sends a batch each time a note ends, and each batch holds many
/// entries per note: one per analysis frame while it sounded, then a final
/// "completed" one. That is far too fine-grained to judge on its own, so
/// entries are collected per bar and a bar is released when either:
///
///  * its last note completes, or
///  * any note of a later bar completes — the player has moved on, so a bar
///    whose last note was never heard still gets judged (with the unheard
///    notes reported as missing) instead of waiting forever.
///
/// Anything left when recording stops is released by [flush].
class PhraseAssembler {
  PhraseAssembler(List<ExpectedNote> notes)
    : _barOf = {for (final n in notes) n.noteId: n.bar},
      _written = notes;

  final Map<int, int> _barOf;
  final List<ExpectedNote> _written;
  final Map<int, List<Notes>> _pending = {};
  final Set<int> _released = {};

  /// Adds one batch from Rust. Returns the bars it completed, in order.
  List<AssembledPhrase> add(List<Notes> batch) {
    var furthestCompletedBar = -1;
    var closedBar = -1;

    for (final entry in batch) {
      final bar = _collect(entry);
      if (bar == null || entry.endTimeMs == null) continue;
      furthestCompletedBar = math.max(furthestCompletedBar, bar);
      if (entry.isEnd) closedBar = math.max(closedBar, bar);
    }

    return _release(
      _pending.keys.where((b) => b < furthestCompletedBar || b <= closedBar),
    );
  }

  /// Releases every bar still holding anything. [leftovers] are entries
  /// Rust had gathered but not yet sent — typically the last note, still
  /// sounding when recording stopped.
  List<AssembledPhrase> flush([List<Notes> leftovers = const []]) {
    for (final entry in leftovers) {
      _collect(entry);
    }
    return _release(_pending.keys);
  }

  /// Files one entry under its bar. Returns the bar, or null when the entry
  /// is not part of this exercise or its bar was already sent.
  int? _collect(Notes entry) {
    final bar = _barOf[entry.noteId.toInt()];
    if (bar == null || _released.contains(bar)) return null;
    _pending.putIfAbsent(bar, () => []).add(entry);
    return bar;
  }

  List<AssembledPhrase> _release(Iterable<int> bars) {
    final ordered = bars.toList()..sort();
    final phrases = <AssembledPhrase>[];
    for (final bar in ordered) {
      final entries = _pending.remove(bar);
      _released.add(bar);
      if (entries == null || entries.isEmpty) continue;
      phrases.add(
        AssembledPhrase(
          number: bar + 1,
          userNotes: longestPerNote(entries),
          expectedNotes: _written
              .where((n) => n.bar == bar)
              .map((n) => n.toBackendJson())
              .toList(),
        ),
      );
    }
    return phrases;
  }

  /// Keeps one entry per note: the longest, which is the completed one when
  /// the note finished. This is the same rule the backend applies, done
  /// here so a bar is a handful of notes on the wire rather than the
  /// hundreds of per-frame entries Rust produces.
  static List<Notes> longestPerNote(List<Notes> entries) {
    final best = <int, Notes>{};
    for (final entry in entries) {
      final id = entry.noteId.toInt();
      final current = best[id];
      if (current == null ||
          (entry.durationMs ?? 0) > (current.durationMs ?? 0)) {
        best[id] = entry;
      }
    }
    final result = best.values.toList()
      ..sort((a, b) => (a.startTimeMs ?? 0).compareTo(b.startTimeMs ?? 0));
    return result;
  }
}
