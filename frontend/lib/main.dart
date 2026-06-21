import 'package:flutter/material.dart';
import 'package:syncfusion_flutter_pdfviewer/pdfviewer.dart';

void main() {
  runApp(const HuAccumponistApp());
}

class HuAccumponistApp extends StatelessWidget {
  const HuAccumponistApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF1A1A2E),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFFE94560),
        ),
      ),
      home: const ScoreViewerPage(),
    );
  }
}

class ScoreViewerPage extends StatelessWidget {
  const ScoreViewerPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // Edge-to-edge canvas layout
      body: SafeArea(
        child: Stack(
          children: [
            // 1. THE PDF VIEWER (Placeholder)
            // Note: Horizontal scrolling is usually preferred for sheet music
            SfPdfViewer.asset(
              'assets/placeholder_score.pdf',
              canShowScrollHead: false, 
              pageLayoutMode: PdfPageLayoutMode.single, 
              scrollDirection: PdfScrollDirection.horizontal, 
            ),

            // 2. FLOATING TOOLBAR (iPad-style)
            Positioned(
              top: 16,
              right: 16,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  // Using the updated .withValues(alpha: x) syntax
                  color: const Color(0xFF16213E).withValues(alpha: 0.85),
                  borderRadius: BorderRadius.circular(30),
                  border: Border.all(
                    color: Colors.white.withValues(alpha: 0.1),
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    IconButton(
                      icon: const Icon(Icons.edit_outlined, size: 22),
                      color: Colors.white,
                      onPressed: () {
                        // TODO: Toggle drawing tools
                      },
                    ),
                    IconButton(
                      icon: const Icon(Icons.more_horiz, size: 22),
                      color: Colors.white,
                      onPressed: () {
                        // TODO: Open menu
                      },
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}