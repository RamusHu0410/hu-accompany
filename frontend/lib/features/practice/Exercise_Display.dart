import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import 'package:hu_accomponist/features/practice/Exercise.dart';
import 'package:hu_accomponist/features/practice/Exercise_Session.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';

/// Shows an exercise in place of the PDF score: its notes by bar, the one
/// to play now, a pulse on every beat, and the count-in.
///
/// The pulse is visual only. An audible click would be picked up by the
/// microphone and could be taken for a played note.
class ExerciseDisplay extends StatefulWidget {
  final ExerciseSession session;
  const ExerciseDisplay({super.key, required this.session});

  @override
  State<ExerciseDisplay> createState() => _ExerciseDisplayState();
}

class _ExerciseDisplayState extends State<ExerciseDisplay>
    with SingleTickerProviderStateMixin {
  late final Ticker _ticker = createTicker(_onTick);

  /// Beat since the downbeat (0 = first note), and the note being played.
  /// Only these trigger a rebuild, not every frame.
  int _beat = -1;
  int _noteIndex = -1;

  ExerciseSession get _session => widget.session;

  @override
  void initState() {
    super.initState();
    _session.addListener(_onSessionChanged);
  }

  @override
  void didUpdateWidget(ExerciseDisplay old) {
    super.didUpdateWidget(old);
    if (old.session != widget.session) {
      old.session.removeListener(_onSessionChanged);
      widget.session.addListener(_onSessionChanged);
    }
  }

  void _onSessionChanged() {
    final running = _session.downbeat != null;
    if (running && !_ticker.isActive) _ticker.start();
    if (!running && _ticker.isActive) {
      _ticker.stop();
      _beat = -1;
      _noteIndex = -1;
    }
    setState(() {});
  }

  void _onTick(Duration _) {
    final downbeat = _session.downbeat;
    if (downbeat == null) return;
    final elapsed =
        DateTime.now().difference(downbeat).inMicroseconds / 1000.0;
    final beat = elapsed < 0 ? -1 : (elapsed / _session.beatMs).floor();
    final note = elapsed < 0
        ? -1
        : _session.notes.indexWhere(
            (n) => elapsed >= n.startMs && elapsed < n.endMs,
          );
    if (beat != _beat || note != _noteIndex) {
      setState(() {
        _beat = beat;
        _noteIndex = note;
      });
    }
  }

  @override
  void dispose() {
    _session.removeListener(_onSessionChanged);
    _ticker.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final notes = _session.notes;
    final bars = <List<int>>[];
    for (var i = 0; i < notes.length; i++) {
      if (bars.length <= notes[i].bar) bars.add([]);
      bars[notes[i].bar].add(i);
    }

    return Stack(
      children: [
        ListView(
          padding: const EdgeInsets.fromLTRB(
            Space.lg,
            Space.xxxl,
            Space.lg,
            Space.xl,
          ),
          children: [
            Text(
              _session.exercise.title,
              style: const TextStyle(
                color: PracticePalette.brown,
                fontSize: 22,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: Space.xxs),
            Text(
              '${_session.bpm} bpm · starting on '
              '${Exercise.noteName(notes.first.midi)}',
              style: const TextStyle(
                color: PracticePalette.mutedBrown,
                fontSize: 13,
              ),
            ),
            const SizedBox(height: Space.lg),
            for (var b = 0; b < bars.length; b++) _bar(b, bars[b], notes),
            const SizedBox(height: Space.md),
            _hint(),
          ],
        ),
        Positioned(top: Space.md, right: Space.md, child: _pulse()),
        if (_session.countIn != null) _countIn(_session.countIn!),
      ],
    );
  }

  Widget _bar(int bar, List<int> indexes, List<ExpectedNote> notes) {
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.sm),
      child: Row(
        children: [
          SizedBox(
            width: 28,
            child: Text(
              '${bar + 1}',
              style: TextStyle(
                color: PracticePalette.mutedBrown.withValues(alpha: 0.6),
                fontSize: 12,
              ),
            ),
          ),
          for (final i in indexes)
            Expanded(
              flex: notes[i].durationMs.round(),
              child: _chip(notes[i], current: i == _noteIndex),
            ),
        ],
      ),
    );
  }

  Widget _chip(ExpectedNote note, {required bool current}) {
    return AnimatedContainer(
      duration: Motion.fast,
      margin: const EdgeInsets.symmetric(horizontal: Space.xxs / 2),
      padding: const EdgeInsets.symmetric(vertical: Space.sm),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: current ? PracticePalette.gold : PracticePalette.ivory,
        borderRadius: Radii.cardRadius,
        border: Border.all(
          color: current ? PracticePalette.gold : PracticePalette.lightGold,
        ),
      ),
      child: Text(
        note.name,
        style: TextStyle(
          color: current ? PracticePalette.paper : PracticePalette.brown,
          fontSize: 14,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }

  /// A dot that pops on every beat once playing has started.
  Widget _pulse() {
    final active = _beat >= 0;
    return TweenAnimationBuilder<double>(
      key: ValueKey(_beat),
      tween: Tween(begin: active ? 1.6 : 1.0, end: 1.0),
      duration: Motion.base,
      curve: Motion.enter,
      builder: (context, scale, _) => Transform.scale(
        scale: scale,
        child: Container(
          width: 14,
          height: 14,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: active
                ? (_beat % Exercise.beatsPerBar == 0
                      ? PracticePalette.gold
                      : PracticePalette.lightGold)
                : PracticePalette.lightGold.withValues(alpha: 0.4),
          ),
        ),
      ),
    );
  }

  Widget _hint() {
    return Text(
      'Tap the mic to start. You get a ${ExerciseSession.countInBeats}-beat '
      'count-in; play the first note on the beat after the last count.',
      style: TextStyle(
        color: PracticePalette.mutedBrown.withValues(alpha: 0.8),
        fontSize: 12,
        height: 1.4,
      ),
    );
  }

  Widget _countIn(int beat) {
    return Positioned.fill(
      child: IgnorePointer(
        child: Container(
          color: PracticePalette.paper.withValues(alpha: 0.85),
          alignment: Alignment.center,
          child: TweenAnimationBuilder<double>(
            key: ValueKey(beat),
            tween: Tween(begin: 1.3, end: 1.0),
            duration: Motion.base,
            curve: Motion.enter,
            builder: (context, scale, child) =>
                Transform.scale(scale: scale, child: child),
            child: Text(
              '$beat',
              style: const TextStyle(
                color: PracticePalette.gold,
                fontSize: 72,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
