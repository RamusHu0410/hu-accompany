import 'dart:ffi' as ffi;
import 'package:flutter/foundation.dart';

/// dart:ffi bridge to the Rust audio capture entry points.
///
/// These are deliberately NOT part of the flutter_rust_bridge API: in
/// native_ffi/src/lib.rs both `listen_audio` and `stop_audio` are marked
/// `#[frb(ignore)]` and exported as plain C symbols, which
/// ios/Runner/recording_bridge.c re-exports under the stable names
/// `start_recording` / `stop_recording`. So src/rust/api.dart has no
/// start/stop function to call — it only exposes initSession, getUserData
/// and notesStream — and capture has to be driven through here.
///
/// Lookup failure is survivable by design. The native library is not
/// currently linked into every target, and a missing symbol must not take
/// the app down: the calls fall back to no-ops that say so once, so the UI
/// still runs and the terminal explains why no audio is arriving.
class AudioNative {
  AudioNative._internal() {
    _init();
  }

  static final AudioNative _instance = AudioNative._internal();
  factory AudioNative() => _instance;

  void Function() _startRecording = _missing('start_recording');
  void Function() _stopRecording = _missing('stop_recording');

  /// True only when both symbols resolved. Callers can use it to explain
  /// the situation rather than silently recording nothing.
  bool isConnected = false;

  static void Function() _missing(String symbol) => () => debugPrint(
        '[Diagnostics] audio: $symbol unavailable — native library not '
        'linked into this build, so no audio is being captured.',
      );

  void _init() {
    try {
      final library = ffi.DynamicLibrary.process();
      _startRecording = library
          .lookup<ffi.NativeFunction<ffi.Void Function()>>('start_recording')
          .asFunction<void Function()>();
      _stopRecording = library
          .lookup<ffi.NativeFunction<ffi.Void Function()>>('stop_recording')
          .asFunction<void Function()>();
      isConnected = true;
      debugPrint('[Diagnostics] audio: native capture bridge connected.');
    } catch (error) {
      // Never rethrow. A missing symbol is expected on targets where the
      // Rust static library has not been linked yet, and the previous
      // version of this class crashed the app at first touch because it
      // rethrew from a static initializer.
      isConnected = false;
      debugPrint(
        '[Diagnostics] audio: native capture bridge NOT available — $error',
      );
    }
  }

  void begin() {
    debugPrint('[Diagnostics] audio: start_recording');
    _startRecording();
  }

  void end() {
    debugPrint('[Diagnostics] audio: stop_recording');
    _stopRecording();
  }
}
