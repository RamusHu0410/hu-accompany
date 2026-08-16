import 'dart:math';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show debugPrint;
import 'package:flutter/services.dart';
import 'LiquidGlass.dart';
import 'Search_Validator.dart';
import 'Send_Strings_2Server.dart';
import 'Pulling_Back_Data.dart';

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

const String _bookFont = 'Georgia';
const List<String> _bookFontFallback = ['Times New Roman', 'Iowan Old Style', 'serif'];
const Color _ink = Color(0xFF3B2E22);

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE — now presented as an open book instead of a plain search list.
// ═══════════════════════════════════════════════════════════════════════════════

class Music_Library_Page extends StatefulWidget {
  const Music_Library_Page({super.key});

  @override
  State<Music_Library_Page> createState() => _Music_Library_PageState();
}

class _Music_Library_PageState extends State<Music_Library_Page> {
  final TextEditingController _search = TextEditingController();
  final FocusNode _focus = FocusNode();
  final PageController _bookPages = PageController();

  // How many results fit neatly on one page of the book before it flips.
  static const int _resultsPerLeaf = 9;

  List<WorkSummary> _results = [];
  bool _hasSearched = false;
  bool _isLoading = false;
  String? _errorMessage;
  final ApiService _api = ApiService();

  List<List<WorkSummary>> get _leaves {
    if (_results.isEmpty) return const [];
    final leaves = <List<WorkSummary>>[];
    for (var i = 0; i < _results.length; i += _resultsPerLeaf) {
      leaves.add(_results.sublist(i, min(i + _resultsPerLeaf, _results.length)));
    }
    return leaves;
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
      if (_bookPages.hasClients) {
        _bookPages.jumpToPage(0);
      }
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
        _openSheet(editions.first);
        return;
      }

      // Multiple versions — let the user pick which one before opening.
      setState(() => _isLoading = false);
      final chosen = await showModalBottomSheet<MusicSheet>(
        context: context,
        backgroundColor: const Color(0xFFF4EEDD),
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        builder: (_) => _EditionPicker(work: work, editions: editions),
      );
      if (chosen != null) _openSheet(chosen);
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
  // then closes the library and hands the result to ScoreViewerPage via
  // the pop result.
  void _openSheet(MusicSheet sheet) async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final pdfBytes = await _api.fetchScorePdf(sheet.id);
      if (!mounted) return;
      Navigator.pop(context, SelectedSheet(sheet: sheet, pdfBytes: pdfBytes));
    } catch (e) {
      setState(() {
        _errorMessage = "Couldn't load that sheet. Please try again.";
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  void dispose() {
    _search.dispose();
    _focus.dispose();
    _bookPages.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light,
      child: Scaffold(
        // A dark "desk" behind the book, so the book itself reads as an
        // object sitting on a surface rather than filling the screen.
        backgroundColor: const Color(0xFF241A12),
        body: SafeArea(
          child: GestureDetector(
            onTap: () => FocusScope.of(context).unfocus(),
            behavior: HitTestBehavior.translucent,
            child: Stack(
              children: [
                const Positioned(top: 12, left: 12, child: _CloseButton()),
                Center(
                  child: LayoutBuilder(
                    builder: (context, constraints) {
                      final w = min(constraints.maxWidth - 24, 720.0);
                      final h = min(constraints.maxHeight - 96, w * 0.66);
                      return _OpenBook(
                        width: w,
                        height: h,
                        leftPage: _searchLeaf(),
                        rightPage: _resultsLeaf(),
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  // ── Left page: title plate + search slot + attribution ──────────────────
  Widget _searchLeaf() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'The Index',
          style: TextStyle(
            fontFamily: _bookFont,
            fontFamilyFallback: _bookFontFallback,
            fontSize: 22,
            fontWeight: FontWeight.w700,
            color: _ink,
            letterSpacing: 0.4,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          'search the collection',
          style: TextStyle(
            fontFamily: _bookFont,
            fontFamilyFallback: _bookFontFallback,
            fontStyle: FontStyle.italic,
            fontSize: 12,
            color: _ink.withValues(alpha: 0.55),
          ),
        ),
        const SizedBox(height: 16),
        Container(
          height: 34,
          decoration: BoxDecoration(
            border: Border(
              bottom: BorderSide(color: _ink.withValues(alpha: 0.45), width: 1),
            ),
          ),
          child: Row(
            children: [
              Icon(Icons.search, size: 16, color: _ink.withValues(alpha: 0.55)),
              const SizedBox(width: 6),
              Expanded(
                child: TextField(
                  controller: _search,
                  focusNode: _focus,
                  textInputAction: TextInputAction.search,
                  onSubmitted: _onSearchSubmitted,
                  style: const TextStyle(
                    fontFamily: _bookFont,
                    fontFamilyFallback: _bookFontFallback,
                    fontSize: 15,
                    color: _ink,
                  ),
                  decoration: InputDecoration(
                    hintText: 'title, composer…',
                    hintStyle: TextStyle(
                      fontFamily: _bookFont,
                      fontFamilyFallback: _bookFontFallback,
                      fontStyle: FontStyle.italic,
                      fontSize: 14,
                      color: _ink.withValues(alpha: 0.35),
                    ),
                    border: InputBorder.none,
                    isDense: true,
                  ),
                  cursorColor: _ink,
                ),
              ),
              if (_search.text.isNotEmpty)
                GestureDetector(
                  onTap: () => setState(_search.clear),
                  child: Icon(Icons.close, size: 14, color: _ink.withValues(alpha: 0.4)),
                ),
            ],
          ),
        ),
        const Spacer(),
        Text(
          'All sheet music is sourced from IMSLP.org',
          style: TextStyle(
            fontFamily: _bookFont,
            fontFamilyFallback: _bookFontFallback,
            fontStyle: FontStyle.italic,
            fontSize: 10,
            color: _ink.withValues(alpha: 0.4),
          ),
        ),
      ],
    );
  }

  // ── Right page: loading / error / empty / results, paginated ────────────
  Widget _resultsLeaf() {
    if (_isLoading) {
      return const Center(
        child: CircularProgressIndicator(strokeWidth: 2, color: _ink),
      );
    }
    if (_errorMessage != null) {
      return Center(
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
    }
    if (!_hasSearched) {
      return Center(
        child: Text(
          'Search to fill this page…',
          style: TextStyle(
            fontFamily: _bookFont,
            fontFamilyFallback: _bookFontFallback,
            fontStyle: FontStyle.italic,
            fontSize: 13,
            color: _ink.withValues(alpha: 0.35),
          ),
        ),
      );
    }
    if (_results.isEmpty) {
      return Center(
        child: Text(
          'No sheet music found.\nTry another search.',
          textAlign: TextAlign.center,
          style: TextStyle(
            fontFamily: _bookFont,
            fontFamilyFallback: _bookFontFallback,
            fontStyle: FontStyle.italic,
            fontSize: 13,
            color: _ink.withValues(alpha: 0.5),
          ),
        ),
      );
    }

    final leaves = _leaves;
    return Column(
      children: [
        Expanded(
          child: PageView.builder(
            controller: _bookPages,
            itemCount: leaves.length,
            itemBuilder: (context, index) {
              return AnimatedBuilder(
                animation: _bookPages,
                builder: (context, child) {
                  double t = 0;
                  if (_bookPages.hasClients && _bookPages.position.haveDimensions) {
                    t = (_bookPages.page ?? index.toDouble()) - index;
                  }
                  final clamped = t.clamp(-1.0, 1.0);
                  final angle = clamped * (pi / 2) * 0.55;
                  return Transform(
                    alignment: Alignment.centerLeft,
                    transform: Matrix4.identity()
                      ..setEntry(3, 2, 0.0016)
                      ..rotateY(angle),
                    child: Opacity(
                      opacity: (1 - clamped.abs() * 0.5).clamp(0.4, 1.0),
                      child: child,
                    ),
                  );
                },
                child: _ResultLeaf(works: leaves[index], onTap: _onWorkTapped),
              );
            },
          ),
        ),
        if (leaves.length > 1) ...[
          const SizedBox(height: 6),
          AnimatedBuilder(
            animation: _bookPages,
            builder: (context, _) {
              final page = _bookPages.hasClients
                  ? (_bookPages.page ?? 0).round()
                  : 0;
              return Text(
                '— page ${page + 1} of ${leaves.length} —',
                style: TextStyle(
                  fontFamily: _bookFont,
                  fontFamilyFallback: _bookFontFallback,
                  fontSize: 10,
                  fontStyle: FontStyle.italic,
                  color: _ink.withValues(alpha: 0.4),
                ),
              );
            },
          ),
        ],
      ],
    );
  }
}

class _ResultLeaf extends StatelessWidget {
  final List<WorkSummary> works;
  final ValueChanged<WorkSummary> onTap;
  const _ResultLeaf({required this.works, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      physics: const NeverScrollableScrollPhysics(),
      padding: EdgeInsets.zero,
      itemCount: works.length,
      separatorBuilder: (_, __) =>
          Divider(height: 10, thickness: 0.6, color: _ink.withValues(alpha: 0.15)),
      itemBuilder: (context, i) {
        final work = works[i];
        return InkWell(
          onTap: () => onTap(work),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    work.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontFamily: _bookFont,
                      fontFamilyFallback: _bookFontFallback,
                      fontSize: 13,
                      color: _ink,
                    ),
                  ),
                ),
                Icon(Icons.chevron_right, size: 14, color: _ink.withValues(alpha: 0.4)),
              ],
            ),
          ),
        );
      },
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// THE BOOK — cover, page-stack thickness, spine gutter shadow.
// ═══════════════════════════════════════════════════════════════════════════════

class _OpenBook extends StatelessWidget {
  final double width;
  final double height;
  final Widget leftPage;
  final Widget rightPage;
  const _OpenBook({
    required this.width,
    required this.height,
    required this.leftPage,
    required this.rightPage,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      height: height,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          // Page-stack thickness peeking out from under the top spread —
          // a few stacked, slightly offset rects behind the main pages.
          for (int i = 3; i >= 1; i--)
            Positioned(
              left: i * 1.4,
              right: i * 1.4,
              top: i * 1.4,
              bottom: -i * 1.4,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: const Color(0xFFE9E0CB).withValues(alpha: 0.9 - i * 0.12),
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
            ),
          // Cast shadow onto the desk beneath the book
          Positioned(
            left: 12,
            right: 12,
            top: 10,
            bottom: -6,
            child: DecoratedBox(
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(6),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.35),
                    blurRadius: 30,
                    offset: const Offset(0, 14),
                  ),
                ],
              ),
            ),
          ),
          // The open spread itself
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: const Color(0xFFF4EEDD),
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: const Color(0xFF6B4A2B), width: 3),
              ),
              child: Row(
                children: [
                  Expanded(child: _PagePaper(spineOnRight: true, child: leftPage)),
                  Container(
                    width: 14,
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [
                          Colors.black.withValues(alpha: 0.0),
                          Colors.black.withValues(alpha: 0.28),
                          Colors.black.withValues(alpha: 0.0),
                        ],
                      ),
                    ),
                  ),
                  Expanded(child: _PagePaper(spineOnRight: false, child: rightPage)),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _PagePaper extends StatelessWidget {
  // true = the spine (gutter shadow) falls along this page's right edge.
  final bool spineOnRight;
  final Widget child;
  const _PagePaper({required this.spineOnRight, required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: spineOnRight ? Alignment.centerRight : Alignment.centerLeft,
          end: spineOnRight ? Alignment.centerLeft : Alignment.centerRight,
          colors: [Colors.black.withValues(alpha: 0.10), Colors.transparent],
          stops: const [0.0, 0.15],
        ),
      ),
      padding: const EdgeInsets.all(18),
      child: child,
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Close page button — top-left corner
// ═══════════════════════════════════════════════════════════════════════════════
class _CloseButton extends StatelessWidget {
  const _CloseButton();
  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => Navigator.pop(context),
      child: LiquidGlass(
        borderRadius: BorderRadius.circular(16),
        blur: 12,
        tintOpacity: 0.22,
        child: const SizedBox(
          width: 32,
          height: 32,
          child: Center(
            child: Icon(
              Icons.close_rounded,
              size: 18,
              color: Color.fromARGB(255, 230, 225, 210),
            ),
          ),
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// EDITION PICKER — bottom sheet shown when a tapped work has more than
// one version (different arrangers/instrumentations/editors).
// ═══════════════════════════════════════════════════════════════════════════════

class _EditionPicker extends StatelessWidget {
  final WorkSummary work;
  final List<MusicSheet> editions;
  const _EditionPicker({required this.work, required this.editions});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 36,
                height: 4,
                margin: const EdgeInsets.only(bottom: 16),
                decoration: BoxDecoration(
                  color: _ink.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            Text(
              work.title,
              style: const TextStyle(
                fontFamily: _bookFont,
                fontFamilyFallback: _bookFontFallback,
                color: _ink,
                fontSize: 17,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              '${editions.length} versions found — choose one',
              style: TextStyle(
                fontFamily: _bookFont,
                fontFamilyFallback: _bookFontFallback,
                fontStyle: FontStyle.italic,
                color: _ink.withValues(alpha: 0.5),
                fontSize: 13,
              ),
            ),
            const SizedBox(height: 14),
            Flexible(
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: editions.length,
                separatorBuilder: (_, __) => const SizedBox(height: 8),
                itemBuilder: (_, i) {
                  final edition = editions[i];
                  return GestureDetector(
                    onTap: () => Navigator.pop(context, edition),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      decoration: BoxDecoration(
                        color: _ink.withValues(alpha: 0.06),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: _ink.withValues(alpha: 0.18)),
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              edition.title,
                              style: const TextStyle(
                                fontFamily: _bookFont,
                                fontFamilyFallback: _bookFontFallback,
                                color: _ink,
                                fontSize: 14,
                                fontWeight: FontWeight.w500,
                              ),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Icon(Icons.chevron_right_rounded, size: 18, color: _ink.withValues(alpha: 0.4)),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}