import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:liquid_glass_easy/liquid_glass_easy.dart';
import 'LiquidGlass.dart';

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

// ─── Swap this list out for your API response ──────────────────────────────────
final List<MusicSheet?> _slots = List.generate(12, (_) => null);
// When backend is ready, do something like:
//   final List<MusicSheet?> _slots = sheets.cast<MusicSheet?>();

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE
// ═══════════════════════════════════════════════════════════════════════════════

class Music_Library_Page extends StatefulWidget {
  const Music_Library_Page({super.key});

  @override
  State<Music_Library_Page> createState() => _Music_Library_PageState();
}

class _Music_Library_PageState extends State<Music_Library_Page> {
  final TextEditingController _search = TextEditingController();
  final FocusNode _focus = FocusNode();
  bool _focused = false;

  List<MusicSheet?> _slots = List.generate(12, (_) => null);
  bool _isLoading = false;
  String? _errorMessage;

  // This helper intercepts the text and manages local states
  void _onSearchSubmitted(String rawQuery) async {
    // 1. Run local structural validation check first
    final validationError = SearchValidator.validateQuery(rawQuery);
    
    if (validationError != null) {
      setState(() {
        _errorMessage = validationError;
        _slots = []; // Wipe previous results or placeholders on failure
      });
      return; // Stop execution right here!
    }

    // 2. If it passes validation, proceed to hit your friend's API endpoint
    setState(() {
      _isLoading = true;
      _errorMessage = null; 
    });

    try {
      // Mocking the network call logic here for context:
      // final results = await MusicSheetService.searchMusic(rawQuery);
      // update your _slots with results...
    } catch (e) {
      setState(() {
        _errorMessage = "Network connection failed.";
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  @override
  void initState() {
    super.initState();
    _focus.addListener(() => setState(() => _focused = _focus.hasFocus));
    _search.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _search.dispose();
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      // Dark status bar icons since the background is now light.
      value: SystemUiOverlayStyle.dark,
      child: Scaffold(
        backgroundColor: const Color.fromARGB(255, 236, 236, 236),
        body: SafeArea(
          bottom: false,
          // LiquidGlassView gives the CloseButton's LiquidGlassLens something
          // to refract on Skia backends (e.g. macOS desktop) instead of
          // silently falling back to a flat frosted look. backgroundWidget
          // is still rendered normally — it's just also captured for the lens.
          child: LiquidGlassView(
            backgroundWidget: Container(
              color: const Color.fromARGB(255, 255, 255, 255),
            ),
            child: GestureDetector(
              onTap: () => FocusScope.of(context).unfocus(),
              behavior: HitTestBehavior.translucent,
              child: Column(
                children: [
                  // ── Top row: close button + search bar ───────────────────────
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      const Padding(
                        padding: EdgeInsets.only(left: 16, top: 24),
                        child: CloseButton(),
                      ),
                      Expanded(
                        child: _SearchBar(
                          controller: _search,
                          focusNode: _focus,
                          focused: _focused,
                        ),
                      ),
                    ],
                  ),

                  // ── Stacked name list ──────────────────────────────────────
                  Expanded(
                    child: ListView.separated(
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 40),
                      itemCount: _slots.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 10),
                      itemBuilder: (_, i) => _NameSlot(sheet: _slots[i]),
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
}

// ═══════════════════════════════════════════════════════════════════════════════
// SEARCH BAR  — light "frosted glass" pill
// ═══════════════════════════════════════════════════════════════════════════════

class _SearchBar extends StatelessWidget {
  final TextEditingController controller;
  final FocusNode focusNode;
  final bool focused;

  const _SearchBar({
    required this.controller,
    required this.focusNode,
    required this.focused,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
        height: 48,
        decoration: BoxDecoration(
          // Glass: layered dark transparency over the light bg + subtle border
          color: focused
              ? Colors.black.withValues(alpha: 0.06)
              : Colors.black.withValues(alpha: 0.035),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: focused
                ? Colors.black.withValues(alpha: 0.14)
                : Colors.black.withValues(alpha: 0.08),
            width: 1,
          ),
          boxShadow: focused
              ? [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.04),
                    blurRadius: 20,
                    spreadRadius: 0,
                  ),
                ]
              : [],
        ),
        child: Row(
          children: [
            const SizedBox(width: 14),
            Icon(
              Icons.search_rounded,
              size: 20,
              color: Colors.black.withValues(alpha: focused ? 0.55 : 0.35),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                controller: controller,
                focusNode: focusNode,
                style: const TextStyle(
                  color: Colors.black87,
                  fontSize: 16,
                  fontWeight: FontWeight.w400,
                  letterSpacing: -0.2,
                ),
                decoration: InputDecoration(
                  hintText: 'Search',
                  hintStyle: TextStyle(
                    color: Colors.black.withValues(alpha: 0.30),
                    fontSize: 16,
                    fontWeight: FontWeight.w400,
                  ),
                  border: InputBorder.none,
                  isDense: true,
                ),
                cursorColor: Colors.black87,
                cursorHeight: 18,
              ),
            ),
            // Clear button
            if (controller.text.isNotEmpty)
              GestureDetector(
                onTap: () => controller.clear(),
                child: Padding(
                  padding: const EdgeInsets.only(right: 12),
                  child: Icon(
                    Icons.cancel,
                    size: 17,
                    color: Colors.black.withValues(alpha: 0.30),
                  ),
                ),
              )
            else
              const SizedBox(width: 14),
          ],
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Close page button — top-left corner, small and subtle
// ═══════════════════════════════════════════════════════════════════════════════
class CloseButton extends StatelessWidget {
  const CloseButton({super.key});
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
              color: Color.fromARGB(255, 180, 180, 180),
            ),
          ),
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// NAME SLOT  — one long horizontal row, empty or filled
// ═══════════════════════════════════════════════════════════════════════════════

class _NameSlot extends StatelessWidget {
  final MusicSheet? sheet;
  const _NameSlot({this.sheet});

  @override
  Widget build(BuildContext context) {
    final isEmpty = sheet == null;

    return GestureDetector(
      onTap: isEmpty ? null : () { /* navigate to ScoreViewerPage */ },
      child: Container(
        height: 56,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        decoration: BoxDecoration(
          color: isEmpty
              ? const Color.fromARGB(255, 180, 180, 180).withValues(alpha: 0.06)
              : const Color.fromARGB(255, 180, 180, 180).withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: const Color.fromARGB(255, 180, 180, 180).withValues(
              alpha: isEmpty ? 0.18 : 0.28,
            ),
            width: 1,
          ),
        ),
        child: Row(
          children: [
            // Small leading icon so a row of text doesn't feel bare
            Icon(
              Icons.music_note_rounded,
              size: 18,
              color: Colors.black.withValues(alpha: isEmpty ? 0.14 : 0.30),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: isEmpty
                  ? const _PlaceholderLine(width: double.infinity, height: 13)
                  : Text(
                      sheet!.title,
                      style: const TextStyle(
                        color: Color.fromARGB(255, 90, 90, 90),
                        fontSize: 15,
                        fontWeight: FontWeight.w500,
                        letterSpacing: -0.2,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
            ),
            if (!isEmpty) ...[
              const SizedBox(width: 8),
              Icon(
                Icons.chevron_right_rounded,
                size: 18,
                color: Colors.black.withValues(alpha: 0.25),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ── Placeholder text line ───────────────────────────────────────────────────

class _PlaceholderLine extends StatelessWidget {
  final double width;
  final double height;
  const _PlaceholderLine({required this.width, required this.height});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(6),
      ),
    );
  }
}