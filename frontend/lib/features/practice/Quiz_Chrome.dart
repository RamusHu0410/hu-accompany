import 'package:flutter/material.dart';

import '../theme/Design_Tokens.dart';
import 'Library_Browse.dart';
import 'Press_Scale.dart';

/// Shared page frame for the quiz screens.
///
/// Reuses the library's cream/serif/gold language — same base colours, same
/// centred serif title with a gold flourish, same 640pt reading column — so
/// the quiz reads as another room in the same building rather than a
/// bolted-on feature.
class QuizScaffold extends StatelessWidget {
  /// The small tracking-spaced label above the title.
  final String label;
  final String title;
  final Widget child;

  /// Shown under the flourish, e.g. the era and its date span.
  final String? subtitle;

  /// Defaults to popping the route.
  final VoidCallback? onClose;

  const QuizScaffold({
    super.key,
    required this.label,
    required this.title,
    required this.child,
    this.subtitle,
    this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: libCream,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(
                Space.lg,
                Space.sm,
                Space.lg,
                0,
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: Text(
                      label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontFamily: libBookFont,
                        fontFamilyFallback: libBookFontFallback,
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 3,
                        color: libInk.withValues(alpha: 0.7),
                      ),
                    ),
                  ),
                  PressScale(
                    onTap: onClose ?? () => Navigator.of(context).maybePop(),
                    borderRadius: Radii.pillRadius,
                    pressedScale: 0.9,
                    child: Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: libCreamCard,
                        border: Border.all(
                          color: libInk.withValues(alpha: 0.16),
                        ),
                      ),
                      child: Icon(
                        Icons.close_rounded,
                        size: 16,
                        color: libInk.withValues(alpha: 0.6),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 640),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: Space.xl),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const SizedBox(height: Space.xs),
                        QuizHeader(title: title, subtitle: subtitle),
                        Expanded(child: child),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Centred serif title with the library's gold rule-dot-rule flourish.
class QuizHeader extends StatelessWidget {
  final String title;
  final String? subtitle;

  const QuizHeader({super.key, required this.title, this.subtitle});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          title,
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontFamily: libBookFont,
            fontFamilyFallback: libBookFontFallback,
            fontSize: 34,
            fontWeight: FontWeight.w700,
            color: libInk,
          ),
        ),
        const SizedBox(height: Space.sm),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _rule(),
            const SizedBox(width: Space.xs),
            Icon(Icons.circle, size: 4, color: libGold.withValues(alpha: 0.7)),
            const SizedBox(width: Space.xs),
            _rule(),
          ],
        ),
        if (subtitle != null) ...[
          const SizedBox(height: Space.sm),
          Text(
            subtitle!,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontFamily: libBookFont,
              fontFamilyFallback: libBookFontFallback,
              fontStyle: FontStyle.italic,
              fontSize: 13,
              color: libInk.withValues(alpha: 0.55),
            ),
          ),
        ],
      ],
    );
  }

  static Widget _rule() => Container(
    width: 32,
    height: 1,
    color: libGold.withValues(alpha: 0.45),
  );
}

/// Small tracking-spaced section heading, matching Library_Browse's own.
class QuizSectionLabel extends StatelessWidget {
  final String text;
  const QuizSectionLabel(this.text, {super.key});

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

/// Inline error/notice in the same italic serif the library uses for its
/// own error text.
class QuizNotice extends StatelessWidget {
  final String message;
  const QuizNotice({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(Space.sm),
      decoration: BoxDecoration(
        color: libGold.withValues(alpha: 0.08),
        borderRadius: Radii.cardRadius,
        border: Border.all(color: libGold.withValues(alpha: 0.3)),
      ),
      child: Text(
        message,
        textAlign: TextAlign.center,
        style: TextStyle(
          fontFamily: libBookFont,
          fontFamilyFallback: libBookFontFallback,
          fontStyle: FontStyle.italic,
          fontSize: 13,
          height: 1.4,
          color: libInk.withValues(alpha: 0.75),
        ),
      ),
    );
  }
}
