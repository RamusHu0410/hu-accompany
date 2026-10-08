import 'dart:io';
import 'dart:typed_data';
import 'dart:ui';

import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

/// Hands a file to the system share sheet (save to Files, AirDrop, mail...).
/// An interface so tests don't open one.
abstract class FileSharer {
  Future<void> share(
    Uint8List bytes, {
    required String filename,
    required String mimeType,
    Rect? origin,
  });
}

class SystemFileSharer implements FileSharer {
  const SystemFileSharer();

  @override
  Future<void> share(
    Uint8List bytes, {
    required String filename,
    required String mimeType,
    Rect? origin,
  }) async {
    final folder = await getTemporaryDirectory();
    final file = File('${folder.path}/$filename');
    await file.writeAsBytes(bytes, flush: true);
    await SharePlus.instance.share(
      ShareParams(
        files: [XFile(file.path, mimeType: mimeType)],
        // iPads anchor the share sheet to the button that opened it.
        sharePositionOrigin: origin,
      ),
    );
  }
}
