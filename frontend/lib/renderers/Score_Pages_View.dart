import 'package:flutter/material.dart';
import '../models/Score_Page_Controller.dart';
import 'Score_Page_Renderer.dart';

/// Vertically scrollable score pages. Each page fills the score area's width,
/// making music readable on phones without covering the app controls.
class Score_Pages_View extends StatefulWidget {
  final ScorePageController controller;

  const Score_Pages_View({super.key, required this.controller});

  @override
  State<Score_Pages_View> createState() => _Score_Pages_ViewState();
}

class _Score_Pages_ViewState extends State<Score_Pages_View> {
  final _scrollController = ScrollController();
  int? _totalPages;

  // Previously a failure here just left _totalPages null forever,
  // causing the view to remain on the loading spinner with no way
  // to tell that the initial score load had actually failed.
  Object? _initialLoadError;

  @override
  void initState() {
    super.initState();

    // Kick off page 1 (and its prefetch of page 2) right away.
    widget.controller
        .warmPage(1)
        .then((_) {
          if (mounted) {
            setState(() {
              _totalPages = widget.controller.totalPages;
            });
          }
        })
        .catchError((Object error) {
          if (mounted) {
            setState(() {
              _initialLoadError = error;
            });
          }
        });
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_initialLoadError != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            "Couldn't load score: $_initialLoadError",
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.black.withValues(alpha: 0.6)),
          ),
        ),
      );
    }

    if (_totalPages == null) {
      return const Center(child: CircularProgressIndicator(strokeWidth: 2.5));
    }

    return Scrollbar(
      controller: _scrollController,
      thumbVisibility: true,
      child: ListView.separated(
        controller: _scrollController,
        padding: const EdgeInsets.fromLTRB(6, 38, 6, 18),
        itemCount: _totalPages!,
        separatorBuilder: (_, _) => const SizedBox(height: 18),
        itemBuilder: (context, index) {
          final pageNumber = index + 1;
          // warmPage also starts the next valid page in the background.
          widget.controller.warmPage(pageNumber);

          return FutureBuilder<RenderedPage>(
            future: widget.controller.getPage(pageNumber),
            builder: (context, snapshot) {
              if (snapshot.hasError) {
                return Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(
                      "Couldn't load page $pageNumber: ${snapshot.error}",
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: Colors.black.withValues(alpha: 0.6),
                      ),
                    ),
                  ),
                );
              }

              if (!snapshot.hasData) {
                return const Center(
                  child: CircularProgressIndicator(strokeWidth: 2.5),
                );
              }

              return snapshot.data!.widget;
            },
          );
        },
      ),
    );
  }
}
