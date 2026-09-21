import 'package:flutter/material.dart';
import 'package:hu_accomponist/shared/theme/Color_Theme.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';
import 'package:hu_accomponist/features/practice/Open_Practice.dart';
import 'package:hu_accomponist/features/shelf/Score_Card.dart';
import 'package:hu_accomponist/features/shelf/Shelf_Empty.dart';
import 'package:hu_accomponist/features/shelf/Shelf_Skeleton.dart';
import 'package:hu_accomponist/features/shelf/Shelf_Manager.dart';

/// The shelf: every sheet the user has actually opened, most recent
/// first, read from on-device storage (see Shelf_Manager.dart). There is
/// no "browse by era" facet in the data the app collects, so sections are
/// drawn from what's genuinely known — recency — rather than an invented
/// classification.
class Shelf_Page extends StatefulWidget {
  const Shelf_Page({super.key});

  @override
  State<Shelf_Page> createState() => _Shelf_PageState();
}

class _Shelf_PageState extends State<Shelf_Page> {
  List<ShelfEntry> _entries = [];
  bool _loading = true;

  static const int _recentCount = 6;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final entries = await ShelfManager.loadAll();
    if (!mounted) return;
    setState(() {
      _entries = entries;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final brightness = MediaQuery.platformBrightnessOf(context);
    final base = ShelfPalette.base(brightness);
    final textColor = ShelfPalette.textColor(brightness);

    return Scaffold(
      backgroundColor: base,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Text(
          'Shelf',
          style: TextStyle(
            color: textColor,
            letterSpacing: 2,
            fontSize: 14,
            fontWeight: FontWeight.w600,
          ),
        ),
        iconTheme: IconThemeData(color: textColor),
      ),
      body: SafeArea(
        // The three states are crossfaded rather than swapped outright, so
        // the skeleton dissolves into the real grid it was standing in for.
        child: AnimatedSwitcher(
          duration: Motion.slow,
          switchInCurve: Motion.enter,
          switchOutCurve: Motion.exit,
          child: _loading
              ? ShelfSkeleton(
                  key: const ValueKey('shelf-loading'),
                  brightness: brightness,
                )
              : _entries.isEmpty
              ? ShelfEmpty(
                  key: const ValueKey('shelf-empty'),
                  textColor: textColor,
                )
              : KeyedSubtree(
                  key: const ValueKey('shelf-content'),
                  child: _sections(brightness, textColor),
                ),
        ),
      ),
    );
  }

  Widget _sections(Brightness brightness, Color textColor) {
    final recent = _entries.take(_recentCount).toList();
    final older = _entries.skip(_recentCount).toList();

    return CustomScrollView(
      physics: AppScroll.physics,
      slivers: [
        _SectionHeader(
          title: older.isEmpty ? 'Your Collection' : 'Recently Played',
          count: recent.length,
          textColor: textColor,
        ),
        _ScoreGrid(entries: recent, brightness: brightness, textColor: textColor),
        if (older.isNotEmpty) ...[
          _SectionHeader(
            title: 'Your Collection',
            count: older.length,
            textColor: textColor,
          ),
          _ScoreGrid(entries: older, brightness: brightness, textColor: textColor),
        ],
        const SliverToBoxAdapter(child: SizedBox(height: Space.xxl)),
      ],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  final int count;
  final Color textColor;
  const _SectionHeader({
    required this.title,
    required this.count,
    required this.textColor,
  });

  @override
  Widget build(BuildContext context) {
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          Space.lg,
          Space.lg,
          Space.lg,
          Space.sm,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: [
            Text(
              title,
              style: TextStyle(
                color: textColor,
                fontSize: 16,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.3,
              ),
            ),
            const SizedBox(width: Space.xs),
            Text(
              '$count',
              style: TextStyle(
                color: textColor.withValues(alpha: 0.4),
                fontSize: 12,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ScoreGrid extends StatelessWidget {
  final List<ShelfEntry> entries;
  final Brightness brightness;
  final Color textColor;
  const _ScoreGrid({
    required this.entries,
    required this.brightness,
    required this.textColor,
  });

  @override
  Widget build(BuildContext context) {
    final subtitleColor = ShelfPalette.subtextColor(brightness);

    return SliverPadding(
      padding: const EdgeInsets.symmetric(horizontal: Space.lg),
      sliver: SliverGrid(
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 3,
          mainAxisSpacing: Space.md,
          crossAxisSpacing: Space.sm,
          childAspectRatio: 0.54,
        ),
        delegate: SliverChildBuilderDelegate((context, i) {
          final entry = entries[i];
          final score = ShelfScore(
            title: entry.title,
            composer: entry.composer,
            meta: _relativeTime(entry.playedAt),
            gradient: ShelfPalette.gradientFor(entry.id),
          );
          return ScoreCard(
            score: score,
            titleColor: textColor,
            subtitleColor: subtitleColor,
            onTap: () => OpenPractice.withShelfEntry(context, entry),
          );
        }, childCount: entries.length),
      ),
    );
  }

  String _relativeTime(DateTime playedAt) {
    final diff = DateTime.now().difference(playedAt);
    if (diff.inMinutes < 1) return 'Just now';
    if (diff.inHours < 1) return '${diff.inMinutes}m ago';
    if (diff.inDays < 1) return '${diff.inHours}h ago';
    if (diff.inDays < 7) return '${diff.inDays}d ago';
    return '${(diff.inDays / 7).floor()}w ago';
  }
}
