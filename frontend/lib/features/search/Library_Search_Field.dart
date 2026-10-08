import 'package:flutter/material.dart';
import 'package:hu_accomponist/shared/theme/Design_Tokens.dart';
import 'package:hu_accomponist/features/search/Library_Browse.dart';

/// The library's search pill.
///
/// Owns its own [FocusNode] and watches the shared [controller] itself.
/// Both of those change on every keystroke and every focus change, and when
/// the page held them it rebuilt the header, the pick strip, the chips and
/// the whole results list on each one — for a border tint and a clear
/// button that live entirely inside this widget.
class LibrarySearchField extends StatefulWidget {
  final TextEditingController controller;

  /// Keeps the clear affordance visible after a search has run, even once
  /// the field itself has been emptied.
  final bool hasSearched;

  final VoidCallback onSubmitted;
  final VoidCallback onClear;

  const LibrarySearchField({
    super.key,
    required this.controller,
    required this.hasSearched,
    required this.onSubmitted,
    required this.onClear,
  });

  @override
  State<LibrarySearchField> createState() => _LibrarySearchFieldState();
}

class _LibrarySearchFieldState extends State<LibrarySearchField> {
  final FocusNode _focus = FocusNode();

  @override
  void initState() {
    super.initState();
    _focus.addListener(_onChanged);
    widget.controller.addListener(_onChanged);
  }

  @override
  void didUpdateWidget(LibrarySearchField old) {
    super.didUpdateWidget(old);
    if (old.controller != widget.controller) {
      old.controller.removeListener(_onChanged);
      widget.controller.addListener(_onChanged);
    }
  }

  void _onChanged() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onChanged);
    _focus.removeListener(_onChanged);
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final focused = _focus.hasFocus;
    final showClear = widget.controller.text.isNotEmpty || widget.hasSearched;

    return AnimatedContainer(
      duration: Motion.base,
      curve: Motion.enter,
      height: 56,
      decoration: BoxDecoration(
        color: libCreamCard,
        borderRadius: Radii.pillRadius,
        border: Border.all(
          color: focused ? libGold : libInk.withValues(alpha: 0.14),
          width: focused ? 1.4 : 1,
        ),
        boxShadow: [
          BoxShadow(
            color: focused
                ? libGold.withValues(alpha: 0.18)
                : Colors.black.withValues(alpha: 0.04),
            blurRadius: focused ? 18 : 8,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Row(
        children: [
          const SizedBox(width: Space.lg),
          AnimatedScale(
            scale: focused ? 1.08 : 1,
            duration: Motion.base,
            curve: Motion.enter,
            child: Icon(
              Icons.search_rounded,
              size: 20,
              color: focused ? libGold : libInk.withValues(alpha: 0.5),
            ),
          ),
          const SizedBox(width: Space.sm),
          Expanded(
            child: TextField(
              controller: widget.controller,
              focusNode: _focus,
              textInputAction: TextInputAction.search,
              onSubmitted: (_) => widget.onSubmitted(),
              style: const TextStyle(
                fontFamily: libBookFont,
                fontFamilyFallback: libBookFontFallback,
                fontSize: 16,
                color: libInk,
              ),
              decoration: InputDecoration(
                hintText: 'Search by title or composer…',
                hintStyle: TextStyle(
                  fontFamily: libBookFont,
                  fontFamilyFallback: libBookFontFallback,
                  fontStyle: FontStyle.italic,
                  fontSize: 15,
                  color: libInk.withValues(alpha: 0.35),
                ),
                border: InputBorder.none,
                isDense: true,
              ),
              cursorColor: libGold,
            ),
          ),
          // Fades rather than popping in on the first character typed.
          AnimatedSwitcher(
            duration: Motion.fast,
            child: showClear
                ? IconButton(
                    key: const ValueKey(true),
                    onPressed: widget.onClear,
                    visualDensity: VisualDensity.compact,
                    icon: Icon(
                      Icons.close_rounded,
                      size: 18,
                      color: libInk.withValues(alpha: 0.4),
                    ),
                  )
                : const SizedBox(key: ValueKey(false), width: Space.lg),
          ),
        ],
      ),
    );
  }
}
