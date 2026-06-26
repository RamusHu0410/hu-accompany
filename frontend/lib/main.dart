import 'package:flutter/material.dart';
import 'package:syncfusion_flutter_pdfviewer/pdfviewer.dart';
import 'DraggableRecorderButton.dart';
import 'DrawingOverlay.dart';         
import 'dart:ffi' as ffi;

typedef StartRecordingFunc = ffi.Void Function();
typedef StartRecordingFuncDart = void Function();
typedef StopRecordingFunc = ffi.Void Function();
typedef StopRecordingFuncDart = void Function();

class NativeBridge {
  late final ffi.DynamicLibrary _nativeLib;
  late final StartRecordingFuncDart _startRecording;
  late final StopRecordingFuncDart _stopRecording;

  NativeBridge() {
    _nativeLib = ffi.DynamicLibrary.executable();
    _startRecording = _nativeLib
        .lookup<ffi.NativeFunction<StartRecordingFunc>>('start_recording')
        .asFunction();
    _stopRecording = _nativeLib
        .lookup<ffi.NativeFunction<StopRecordingFunc>>('stop_recording')
        .asFunction();
  }
}

final NativeBridge _nativeBridge = NativeBridge();

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
        colorScheme: const ColorScheme.dark(primary: Color(0xFFE94560)),
      ),
      home: const ScoreViewerPage(),
    );
  }
}

// ↓ Changed to StatefulWidget to track drawing mode
class ScoreViewerPage extends StatefulWidget {
  const ScoreViewerPage({super.key});

  @override
  State<ScoreViewerPage> createState() => _ScoreViewerPageState();
}

class _ScoreViewerPageState extends State<ScoreViewerPage> {
  bool _isDrawingMode = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: [
            // LAYER 1: PDF Viewer
            Positioned.fill(
              child: SfPdfViewer.asset(
                'assets/placeholder_score.pdf',
                canShowScrollHead: false,
                pageLayoutMode: PdfPageLayoutMode.single,
                scrollDirection: PdfScrollDirection.horizontal,
              ),
            ),

            // LAYER 2: Drawing overlay (transparent when not drawing)
            DrawingOverlay(isDrawingMode: _isDrawingMode),

            // LAYER 3: Floating Toolbar
            Positioned(
              top: 16,
              right: 16,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF16213E).withValues(alpha: 0.85),
                  borderRadius: BorderRadius.circular(30),
                  border: Border.all(color: Colors.white.withValues(alpha: 0.1)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Pen button — highlights red when active
                    IconButton(
                      icon: Icon(
                        Icons.edit_outlined,
                        size: 22,
                        color: _isDrawingMode
                            ? const Color(0xFFE94560)
                            : Colors.white,
                      ),
                      onPressed: () {
                        setState(() => _isDrawingMode = !_isDrawingMode);
                      },
                    ),
                    IconButton(
                      icon: const Icon(Icons.more_horiz, size: 22),
                      color: Colors.white,
                      onPressed: () {},
                    ),
                  ],
                ),
              ),
            ),

            // LAYER 4: Draggable Recorder Button
            DraggableRecorderButton(
              onToggle: (isRecording) {
                if (isRecording) {
                  _nativeBridge._startRecording();
                } else {
                  _nativeBridge._stopRecording();
                }
              },
            ),
          ],
        ),
      ),
    );
  }
}