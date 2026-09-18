import 'package:flutter/material.dart';

// ─── Shared library styling ──────────────────────────────────────────────────
const String libBookFont = 'Georgia';
const List<String> libBookFontFallback = [
  'Times New Roman',
  'Iowan Old Style',
  'serif',
];
const Color libInk = Color(0xFF2C2113);
const Color libGold = Color(0xFF8A6D2F);
const Color libCream = Color(0xFFF6EFDD);
const Color libCreamCard = Color(0xFFFFFBF2);

/// A piece the user can jump straight back into — a featured pick, a
/// recently opened score, or a saved favourite.
class LibraryPick {
  final String title;
  final String composer;
  const LibraryPick({required this.title, required this.composer});
}

/// Session-scoped recents/favourites. There's no persistence layer yet, so
/// this resets on relaunch — swap the two lists for real storage when one
/// exists, without touching any of the widgets below.
class LibraryShelfStore {
  LibraryShelfStore._();

  static final List<LibraryPick> recents = [];
  static final List<LibraryPick> favorites = [];

  static void remember(LibraryPick pick) {
    recents.removeWhere((p) => p.title == pick.title);
    recents.insert(0, pick);
    if (recents.length > 12) recents.removeLast();
  }

  static bool isFavorite(String title) =>
      favorites.any((p) => p.title == title);

  static void toggleFavorite(LibraryPick pick) {
    if (isFavorite(pick.title)) {
      favorites.removeWhere((p) => p.title == pick.title);
    } else {
      favorites.insert(0, pick);
    }
  }
}

const List<LibraryPick> kFeaturedPicks = [
  LibraryPick(title: 'Clair de Lune', composer: 'Debussy'),
  LibraryPick(title: 'Für Elise', composer: 'Beethoven'),
  LibraryPick(title: 'Nocturne Op. 9 No. 2', composer: 'Chopin'),
  LibraryPick(title: 'Gymnopédie No. 1', composer: 'Satie'),
  LibraryPick(title: 'Air on the G String', composer: 'Bach'),
  LibraryPick(title: 'Ave Maria', composer: 'Schubert'),
];

// ═════════════════════════════════════════════════════════════════════════════
// FEATURED / RECENTLY PLAYED — a horizontal strip of tappable cards.
// ═════════════════════════════════════════════════════════════════════════════

class LibraryPickStrip extends StatelessWidget {
  final String label;
  final List<LibraryPick> picks;
  final ValueChanged<LibraryPick> onTap;

  const LibraryPickStrip({
    super.key,
    required this.label,
    required this.picks,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SectionLabel(label),
        const SizedBox(height: 10),
        SizedBox(
          height: 112,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            clipBehavior: Clip.none,
            itemCount: picks.length,
            separatorBuilder: (_, _) => const SizedBox(width: 10),
            itemBuilder: (_, i) =>
                _PickCard(pick: picks[i], onTap: () => onTap(picks[i])),
          ),
        ),
      ],
    );
  }
}

class _PickCard extends StatelessWidget {
  final LibraryPick pick;
  final VoidCallback onTap;
  const _PickCard({required this.pick, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Container(
          width: 150,
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
          decoration: BoxDecoration(
            color: libCreamCard,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: libInk.withValues(alpha: 0.10)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 28,
                height: 28,
                decoration: BoxDecoration(
                  color: libGold.withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(
                  Icons.play_arrow_rounded,
                  size: 18,
                  color: libGold,
                ),
              ),
              const Spacer(),
              Text(
                pick.title,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontFamily: libBookFont,
                  fontFamilyFallback: libBookFontFallback,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  height: 1.2,
                  color: libInk,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                pick.composer,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontFamily: libBookFont,
                  fontFamilyFallback: libBookFontFallback,
                  fontStyle: FontStyle.italic,
                  fontSize: 11,
                  color: libInk.withValues(alpha: 0.5),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// FILTER CHIPS — each opens a short preset menu that seeds the search.
// ═════════════════════════════════════════════════════════════════════════════

const Map<String, List<String>> kLibraryFilters = {
  'Composer': ['Bach', 'Mozart', 'Beethoven', 'Chopin', 'Debussy', 'Satie'],
  'Era': ['Baroque', 'Classical', 'Romantic', 'Impressionist'],
  'Difficulty': ['Beginner', 'Intermediate', 'Advanced'],
};

class LibraryFilterChips extends StatelessWidget {
  /// Filter name → the value currently picked for it, if any.
  final Map<String, String> selected;
  final void Function(String filter, String? value) onChanged;

  const LibraryFilterChips({
    super.key,
    required this.selected,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: kLibraryFilters.entries.map((entry) {
        final value = selected[entry.key];
        return Padding(
          padding: const EdgeInsets.only(right: 8),
          child: _FilterChip(
            label: value ?? entry.key,
            active: value != null,
            options: entry.value,
            onSelected: (v) => onChanged(entry.key, v),
            onCleared: () => onChanged(entry.key, null),
          ),
        );
      }).toList(),
    );
  }
}

class _FilterChip extends StatelessWidget {
  final String label;
  final bool active;
  final List<String> options;
  final ValueChanged<String> onSelected;
  final VoidCallback onCleared;

  const _FilterChip({
    required this.label,
    required this.active,
    required this.options,
    required this.onSelected,
    required this.onCleared,
  });

  @override
  Widget build(BuildContext context) {
    return PopupMenuButton<String>(
      color: libCreamCard,
      position: PopupMenuPosition.under,
      onSelected: onSelected,
      itemBuilder: (_) => options
          .map(
            (o) => PopupMenuItem<String>(
              value: o,
              height: 40,
              child: Text(
                o,
                style: const TextStyle(
                  fontFamily: libBookFont,
                  fontFamilyFallback: libBookFontFallback,
                  fontSize: 14,
                  color: libInk,
                ),
              ),
            ),
          )
          .toList(),
      child: Container(
        padding: const EdgeInsets.fromLTRB(14, 8, 10, 8),
        decoration: BoxDecoration(
          color: active ? libGold.withValues(alpha: 0.12) : libCreamCard,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(
            color: active ? libGold : libInk.withValues(alpha: 0.14),
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: TextStyle(
                fontFamily: libBookFont,
                fontFamilyFallback: libBookFontFallback,
                fontSize: 13,
                fontWeight: active ? FontWeight.w700 : FontWeight.w500,
                color: active ? libGold : libInk.withValues(alpha: 0.7),
              ),
            ),
            const SizedBox(width: 4),
            GestureDetector(
              onTap: active ? onCleared : null,
              child: Icon(
                active ? Icons.close_rounded : Icons.expand_more_rounded,
                size: 15,
                color: active ? libGold : libInk.withValues(alpha: 0.45),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// QUICK CATEGORIES — four tiles that swap what the idle page is showing.
// ═════════════════════════════════════════════════════════════════════════════

enum LibraryCategory { recent, favorites, collections, browse }

class QuickCategoryRow extends StatelessWidget {
  final LibraryCategory selected;
  final ValueChanged<LibraryCategory> onSelected;

  const QuickCategoryRow({
    super.key,
    required this.selected,
    required this.onSelected,
  });

  static const _tiles = {
    LibraryCategory.recent: (Icons.history_rounded, 'Recent'),
    LibraryCategory.favorites: (Icons.star_border_rounded, 'Favorites'),
    LibraryCategory.collections: (Icons.inventory_2_outlined, 'Collections'),
    LibraryCategory.browse: (Icons.auto_awesome_outlined, 'Browse'),
  };

  @override
  Widget build(BuildContext context) {
    return Row(
      children: _tiles.entries.map((entry) {
        final (icon, label) = entry.value;
        final active = entry.key == selected;
        return Expanded(
          child: Padding(
            padding: const EdgeInsets.only(right: 8),
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: () => onSelected(entry.key),
                borderRadius: BorderRadius.circular(14),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 160),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                  decoration: BoxDecoration(
                    color: active
                        ? libGold.withValues(alpha: 0.12)
                        : libCreamCard,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: active ? libGold : libInk.withValues(alpha: 0.10),
                    ),
                  ),
                  child: Column(
                    children: [
                      Icon(
                        icon,
                        size: 19,
                        color: active ? libGold : libInk.withValues(alpha: 0.55),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        label,
                        style: TextStyle(
                          fontFamily: libBookFont,
                          fontFamilyFallback: libBookFontFallback,
                          fontSize: 11,
                          fontWeight: active
                              ? FontWeight.w700
                              : FontWeight.w500,
                          color: active ? libGold : libInk.withValues(alpha: 0.6),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        );
      }).toList(),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  final String text;
  const _SectionLabel(this.text);

  @override
  Widget build(BuildContext context) {
    return Text(
      text.toUpperCase(),
      style: TextStyle(
        fontFamily: libBookFont,
        fontFamilyFallback: libBookFontFallback,
        fontSize: 10,
        fontWeight: FontWeight.w700,
        letterSpacing: 2,
        color: libInk.withValues(alpha: 0.45),
      ),
    );
  }
}

/// Shared by the library's idle states — a centered icon + message, used
/// where a category has nothing to show yet.
class LibraryEmptyNote extends StatelessWidget {
  final IconData icon;
  final String message;
  const LibraryEmptyNote({
    super.key,
    required this.icon,
    required this.message,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 26, color: libInk.withValues(alpha: 0.22)),
          const SizedBox(height: 10),
          Text(
            message,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: libBookFont,
              fontFamilyFallback: libBookFontFallback,
              fontStyle: FontStyle.italic,
              fontSize: 13,
              height: 1.4,
              color: libInk.withValues(alpha: 0.42),
            ),
          ),
        ],
      ),
    );
  }
}
