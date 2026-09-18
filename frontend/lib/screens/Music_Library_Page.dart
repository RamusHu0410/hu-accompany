import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../utils/Search_Validator.dart';
import '../services/Send_Strings_2Server.dart';
import '../services/Pulling_Back_Data.dart';
import '../widgets/Library_Browse.dart';
import '../widgets/Library_Result_Card.dart';
import '../widgets/Library_Edition_Picker.dart';
import '../widgets/Library_Search_Field.dart';
import '../widgets/Library_Skeleton.dart';
import '../theme/Design_Tokens.dart';
import 'Shelf_Page.dart';
import '../models/Shelf_Manager.dart';

// ─── Plug your real data in here later ────────────────────────────────────────
class MusicSheet {
  final String id;
  final String title;
  final String? thumbnailUrl;
  final String pdfUrl;

  const MusicSheet({
    required this.id,
    required this.title,
    this.thumbnailUrl,
    required this.pdfUrl,
  });
}

/// What gets handed back to ScoreViewerPage when the user picks a sheet:
/// the sheet itself, plus the PDF bytes already fetched for it, so the
/// viewer doesn't have to make a second request.
class SelectedSheet {
  final MusicSheet sheet;
  final Uint8List pdfBytes;
  const SelectedSheet({required this.sheet, required this.pdfBytes});
}

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

  List<WorkSummary> _results = [];
  bool _hasSearched = false;
  bool _isLoading = false;
  String? _errorMessage;
  final ApiService _api = ApiService();

  final Map<String, String> _filters = {};
  LibraryCategory _category = LibraryCategory.browse;

  /// True while the page is showing its browsable front matter rather than
  /// the outcome of a search.
  bool get _isBrowsing =>
      !_hasSearched && !_isLoading && _errorMessage == null;

  /// Filter chips are search shortcuts, not a separate facet system — the
  /// picked values are folded into the same query string the field sends.
  String get _composedQuery =>
      [_search.text.trim(), ..._filters.values].where((s) => s.isNotEmpty).join(' ');

  void _onFilterChanged(String filter, String? value) {
    setState(() {
      if (value == null) {
        _filters.remove(filter);
      } else {
        _filters[filter] = value;
      }
    });
    if (_composedQuery.isNotEmpty) _onSearchSubmitted(_composedQuery);
  }

  void _resetToBrowse() {
    setState(() {
      _search.clear();
      _filters.clear();
      _results = [];
      _hasSearched = false;
      _errorMessage = null;
    });
  }

  // This helper intercepts the text and manages local states
  void _onSearchSubmitted(String rawQuery) async {
    // 1. Run local structural validation check first
    final validationError = SearchValidator.validateQuery(rawQuery);

    if (validationError != null) {
      setState(() {
        _errorMessage = validationError;
        _results = []; // Wipe previous results on failure
      });
      return; // Stop execution right here!
    }

    // 2. If it passes validation, proceed to hit your friend's API endpoint
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final results = await MusicSheetService.searchMusic(rawQuery);
      setState(() {
        _results = results;
        _hasSearched = true;
      });
    } catch (e) {
      debugPrint('MusicSheetService.searchMusic failed: $e');
      setState(() {
        _errorMessage = "Network connection failed.";
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  // Fires when a work row is tapped. A "work" here may have one edition
  // or several (different arrangers/instrumentations/editors) — we don't
  // know which until we ask, so this always fetches first.
  void _onWorkTapped(WorkSummary work) async {
    LibraryShelfStore.remember(
      LibraryPick(title: work.title, composer: work.composer),
    );
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final editions = await MusicSheetService.fetchWorkEditions(work.title);

      if (!mounted) return;

      if (editions.isEmpty) {
        setState(() {
          _errorMessage = "No sheet music found for that piece.";
          _isLoading = false;
        });
        return;
      }

      if (editions.length == 1) {
        setState(() => _isLoading = false);
        _openSheet(editions.first, composer: work.composer);
        return;
      }

      // Multiple versions — let the user pick which one before opening.
      setState(() => _isLoading = false);
      final chosen = await showModalBottomSheet<MusicSheet>(
        context: context,
        backgroundColor: _cream,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(Radii.modal),
          ),
        ),
        builder: (_) => LibraryEditionPicker(work: work, editions: editions),
      );
      if (chosen != null) _openSheet(chosen, composer: work.composer);
    } catch (e) {
      debugPrint('fetchWorkEditions failed: $e');
      if (!mounted) return;
      setState(() {
        _errorMessage = "Couldn't load versions for that piece.";
        _isLoading = false;
      });
    }
  }

  // Fires when a result row is tapped. Fetches the PDF for that one sheet,
  // records it on the shelf, then closes the library and hands the
  // result to ScoreViewerPage via the pop result.
  void _openSheet(MusicSheet sheet, {required String composer}) async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final pdfBytes = await _api.fetchScorePdf(sheet.id);
      if (!mounted) return;
      ShelfManager.recordPlay(
        id: sheet.id,
        title: sheet.title,
        composer: composer,
      );
      Navigator.pop(context, SelectedSheet(sheet: sheet, pdfBytes: pdfBytes));
    } catch (e) {
      setState(() {
        // fetchScorePdf now surfaces the backend's actual reason (e.g.
        // IMSLP's daily anonymous-download quota being hit) rather than a
        // generic status code — show that directly instead of masking it.
        _errorMessage = _friendlyError(e);
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  // Strips Dart's default "Exception: " prefix so backend-provided error
  // text reads naturally in the UI.
  String _friendlyError(Object e) {
    final msg = e.toString();
    return msg.startsWith('Exception: ') ? msg.substring(11) : msg;
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.dark,
      child: Scaffold(
        backgroundColor: _cream,
        body: SafeArea(
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
                              visible: _isBrowsing,
                              child: Padding(
                                padding: const EdgeInsets.only(top: 22),
                                child: _pickStrip(),
                              ),
                            ),
                            const SizedBox(height: Space.lg),
                            LibrarySearchField(
                              controller: _search,
                              hasSearched: _hasSearched,
                              onSubmitted: () =>
                                  _onSearchSubmitted(_composedQuery),
                              onClear: _resetToBrowse,
                            ),
                            const SizedBox(height: Space.sm),
                            LibraryFilterChips(
                              selected: _filters,
                              onChanged: _onFilterChanged,
                            ),
                            _collapsible(
                              visible: _isBrowsing,
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
            Container(width: 32, height: 1, color: _gold.withValues(alpha: 0.45)),
            const SizedBox(width: 8),
            Icon(Icons.circle, size: 4, color: _gold.withValues(alpha: 0.7)),
            const SizedBox(width: 8),
            Container(width: 32, height: 1, color: _gold.withValues(alpha: 0.45)),
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
    _onSearchSubmitted(pick.title);
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

    if (_isLoading) {
      key = const ValueKey('loading');
      child = const LibrarySkeleton();
    } else if (_errorMessage != null) {
      key = ValueKey('error_${_errorMessage.hashCode}');
      child = Center(
        child: Text(
          _errorMessage!,
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
    } else if (!_hasSearched) {
      key = ValueKey('category_${_category.name}');
      child = _categoryContent();
    } else if (_results.isEmpty) {
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
      key = ValueKey('results_${_results.length}_${_results.first.title}');
      child = ListView.separated(
        key: key,
        physics: AppScroll.physics,
        padding: const EdgeInsets.only(bottom: Space.xl),
        itemCount: _results.length,
        separatorBuilder: (_, _) => const SizedBox(height: Space.sm),
        itemBuilder: (context, i) {
          final work = _results[i];
          return LibraryResultCard(
            title: work.title,
            composer: work.composer,
            onTap: () => _onWorkTapped(work),
            onFavorite: () => _toggleFavorite(
              LibraryPick(title: work.title, composer: work.composer),
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
              'All sheet music is sourced from IMSLP.org',
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
