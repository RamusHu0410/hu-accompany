import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:hu_accomponist/features/search/Library_Browse.dart';
import 'package:hu_accomponist/features/search/Library_Result_Card.dart';
import 'package:hu_accomponist/features/search/Library_Search_Field.dart';
import 'package:hu_accomponist/features/search/Library_Skeleton.dart';
import 'package:hu_accomponist/features/search/library_controller.dart';
import 'package:hu_accomponist/integrations/scores/score_models.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';
import 'package:hu_accomponist/features/shelf/Shelf_Page.dart';

// Styling lives in Library_Browse.dart so the page and its browse
// components can't drift apart.
const String _bookFont = libBookFont;
const List<String> _bookFontFallback = libBookFontFallback;
const Color _ink = libInk;
const Color _gold = libGold;
const Color _cream = libCream;

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE — a clean, flat search page (no skeuomorphic book) in the same
// warm-cream / classical-serif / gold-accent style used elsewhere.
// ═══════════════════════════════════════════════════════════════════════════════

class Music_Library_Page extends StatefulWidget {
  const Music_Library_Page({super.key});

  @override
  State<Music_Library_Page> createState() => _Music_Library_PageState();
}

class _Music_Library_PageState extends State<Music_Library_Page> {
  final TextEditingController _search = TextEditingController();
  final LibraryController _library = LibraryController();

  final Map<String, String> _filters = {};
  LibraryCategory _category = LibraryCategory.browse;

  /// Filter chips are search shortcuts, not a separate facet system — the
  /// picked values are folded into the same query string the field sends.
  String get _composedQuery => [
    _search.text.trim(),
    ..._filters.values,
  ].where((s) => s.isNotEmpty).join(' ');

  void _onFilterChanged(String filter, String? value) {
    setState(() {
      if (value == null) {
        _filters.remove(filter);
      } else {
        _filters[filter] = value;
      }
    });
    if (_composedQuery.isNotEmpty) _library.search(_composedQuery);
  }

  void _resetToBrowse() {
    setState(() {
      _search.clear();
      _filters.clear();
    });
    _library.reset();
  }

  // Loads the tapped score, then closes the library and hands it to
  // whoever opened it via the pop result.
  Future<void> _openScore(ScoreSummary score) async {
    final loaded = await _library.open(score);
    if (loaded != null && mounted) Navigator.pop(context, loaded);
  }

  @override
  void dispose() {
    _search.dispose();
    _library.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.dark,
      child: Scaffold(
        backgroundColor: _cream,
        body: ListenableBuilder(
          listenable: _library,
          builder: (context, _) => SafeArea(
            child: GestureDetector(
              onTap: () => FocusScope.of(context).unfocus(),
              behavior: HitTestBehavior.translucent,
              child: Column(
                children: [
                  _topBar(context),
                  Expanded(
                    child: Center(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 640),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 24),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              const SizedBox(height: 8),
                              _header(),
                              // The strip and the category row are front
                              // matter — they fold away once a search is in
                              // flight so results get the full height.
                              _collapsible(
                                visible: _library.isBrowsing,
                                child: Padding(
                                  padding: const EdgeInsets.only(top: 22),
                                  child: _pickStrip(),
                                ),
                              ),
                              const SizedBox(height: Space.lg),
                              LibrarySearchField(
                                controller: _search,
                                hasSearched: _library.hasSearched,
                                onSubmitted: () =>
                                    _library.search(_composedQuery),
                                onClear: _resetToBrowse,
                              ),
                              const SizedBox(height: Space.sm),
                              LibraryFilterChips(
                                selected: _filters,
                                onChanged: _onFilterChanged,
                              ),
                              _collapsible(
                                visible: _library.isBrowsing,
                                child: Padding(
                                  padding: const EdgeInsets.only(top: 14),
                                  child: QuickCategoryRow(
                                    selected: _category,
                                    onSelected: _onCategorySelected,
                                  ),
                                ),
                              ),
                              const SizedBox(height: 16),
                              Expanded(child: _resultsArea()),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  // ── Top bar: small label left, close button right ───────────────────────
  Widget _topBar(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            'MUSIC LIBRARY',
            style: TextStyle(
              fontFamily: _bookFont,
              fontFamilyFallback: _bookFontFallback,
              fontSize: 12,
              fontWeight: FontWeight.w700,
              letterSpacing: 3,
              color: _ink.withValues(alpha: 0.7),
            ),
          ),
          const LibraryCloseButton(),
        ],
      ),
    );
  }

  // ── Header: title, thin gold flourish ───────────────────────────────────
  Widget _header() {
    return Column(
      children: [
        const Text(
          'The Index',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: _bookFont,
            fontFamilyFallback: _bookFontFallback,
            fontSize: 34,
            fontWeight: FontWeight.w700,
            color: _ink,
          ),
        ),
        const SizedBox(height: 10),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 32,
              height: 1,
              color: _gold.withValues(alpha: 0.45),
            ),
            const SizedBox(width: 8),
            Icon(Icons.circle, size: 4, color: _gold.withValues(alpha: 0.7)),
            const SizedBox(width: 8),
            Container(
              width: 32,
              height: 1,
              color: _gold.withValues(alpha: 0.45),
            ),
          ],
        ),
      ],
    );
  }

  // Front matter folds away instead of snapping, so the results area
  // growing doesn't feel like a page swap.
  Widget _collapsible({required bool visible, required Widget child}) {
    return AnimatedSize(
      duration: Motion.base,
      curve: Motion.enter,
      alignment: Alignment.topCenter,
      child: visible ? child : const SizedBox(width: double.infinity),
    );
  }

  // Recently played once there's history, curated picks before that.
  Widget _pickStrip() {
    final recents = LibraryShelfStore.recents;
    return LibraryPickStrip(
      label: recents.isEmpty ? 'Featured' : 'Recently played',
      picks: recents.isEmpty ? kFeaturedPicks : recents,
      onTap: _onPickTapped,
    );
  }

  void _onPickTapped(LibraryPick pick) {
    _search.text = pick.title;
    _library.search(pick.title);
  }

  void _onCategorySelected(LibraryCategory category) {
    if (category == LibraryCategory.collections) {
      Navigator.of(
        context,
      ).push(MaterialPageRoute(builder: (_) => const Shelf_Page()));
      return;
    }
    setState(() => _category = category);
  }

  // ── Results area: loading / error / prompt / empty / list, all
  // cross-faded smoothly rather than snapping between states ──────────────
  Widget _resultsArea() {
    Widget child;
    Key key;

    if (_library.isLoading) {
      key = const ValueKey('loading');
      child = const LibrarySkeleton();
    } else if (_library.errorMessage != null) {
      key = ValueKey('error_${_library.errorMessage.hashCode}');
      child = Center(
        child: Text(
          _library.errorMessage!,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: _bookFont,
            fontFamilyFallback: _bookFontFallback,
            fontStyle: FontStyle.italic,
            fontSize: 14,
            color: _ink.withValues(alpha: 0.7),
          ),
        ),
      );
    } else if (!_library.hasSearched) {
      key = ValueKey('category_${_category.name}');
      child = _categoryContent();
    } else if (_library.results.isEmpty) {
      key = const ValueKey('no_results');
      child = Center(
        child: Text(
          'No sheet music found.\nTry another search.',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: _bookFont,
            fontFamilyFallback: _bookFontFallback,
            fontStyle: FontStyle.italic,
            fontSize: 14,
            color: _ink.withValues(alpha: 0.5),
          ),
        ),
      );
    } else {
      final results = _library.results;
      key = ValueKey('results_${results.length}_${results.first.id}');
      child = ListView.separated(
        key: key,
        physics: AppScroll.physics,
        padding: const EdgeInsets.only(bottom: Space.xl),
        itemCount: results.length,
        separatorBuilder: (_, _) => const SizedBox(height: Space.sm),
        itemBuilder: (context, i) {
          final score = results[i];
          return LibraryResultCard(
            title: score.title,
            composer: score.composer,
            onTap: () => _openScore(score),
            onFavorite: () => _toggleFavorite(
              LibraryPick(title: score.title, composer: score.composer),
            ),
          );
        },
      );
    }

    return AnimatedSwitcher(
      duration: Motion.slow,
      switchInCurve: Motion.enter,
      switchOutCurve: Motion.exit,
      transitionBuilder: (child, animation) => FadeTransition(
        opacity: animation,
        child: SlideTransition(
          position: Tween<Offset>(
            begin: const Offset(0, 0.03),
            end: Offset.zero,
          ).animate(animation),
          child: child,
        ),
      ),
      child: KeyedSubtree(key: key, child: child),
    );
  }

  // ── Idle content: whichever quick category is selected ──────────────────
  Widget _categoryContent() {
    switch (_category) {
      case LibraryCategory.recent:
        return LibraryShelfStore.recents.isEmpty
            ? const LibraryEmptyNote(
                icon: Icons.history_rounded,
                message: 'Nothing opened yet.\nScores you open appear here.',
              )
            : _pickList(LibraryShelfStore.recents);
      case LibraryCategory.favorites:
        return LibraryShelfStore.favorites.isEmpty
            ? const LibraryEmptyNote(
                icon: Icons.star_border_rounded,
                message: 'No favourites yet.\nTap the star on any result.',
              )
            : _pickList(LibraryShelfStore.favorites);
      case LibraryCategory.collections:
      case LibraryCategory.browse:
        return _pickList(kFeaturedPicks, footer: true);
    }
  }

  Widget _pickList(List<LibraryPick> picks, {bool footer = false}) {
    return ListView.separated(
      physics: AppScroll.physics,
      padding: const EdgeInsets.only(bottom: Space.xl),
      itemCount: picks.length + (footer ? 1 : 0),
      separatorBuilder: (_, _) => const SizedBox(height: Space.sm),
      itemBuilder: (context, i) {
        if (i == picks.length) {
          return Padding(
            padding: const EdgeInsets.only(top: 14),
            child: Text(
              'Sheet music from PDMX, a public-domain MusicXML collection',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: _bookFont,
                fontFamilyFallback: _bookFontFallback,
                fontStyle: FontStyle.italic,
                fontSize: 11,
                color: _ink.withValues(alpha: 0.4),
              ),
            ),
          );
        }
        final pick = picks[i];
        return LibraryResultCard(
          title: pick.title,
          composer: pick.composer,
          onTap: () => _onPickTapped(pick),
          onFavorite: () => _toggleFavorite(pick),
        );
      },
    );
  }

  void _toggleFavorite(LibraryPick pick) {
    setState(() => LibraryShelfStore.toggleFavorite(pick));
  }
}
