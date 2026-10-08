import 'dart:convert';
import 'dart:ffi' as ffi;
import 'dart:io' show Platform;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Something wrong with audio capture, as reported by the Rust engine.
class AudioProblem {
  const AudioProblem(this.code, this.message);

  /// Codes of native_ffi/src/audio.rs.
  final int code;
  final String message;

  /// From this code on the engine still analyses audio (for example a
  /// microphone that only delivers silence); below it capture has failed.
  static const int firstWarning = 100;

  bool get isFatal => code < firstWarning;

  @override
  String toString() => 'AudioProblem($code: $message)';
}

/// dart:ffi bridge to the Rust audio capture entry points.
///
/// These are deliberately NOT part of the flutter_rust_bridge API: in
/// native_ffi/src/lib.rs `listen_audio`, `stop_audio`, `audio_status` and
/// `audio_error_message` are marked `#[frb(ignore)]` and exported as plain C
/// symbols, which ios/recording_bridge.c re-exports under the stable names
/// `start_recording` / `stop_recording` / `recording_status` /
/// `recording_message`. So src/rust/api.dart has no start/stop function to
/// call — it only exposes initSession, getUserData and notesStream — and
/// capture has to be driven through here.
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

  /// iOS only. The Rust engine opens the microphone itself and never asks
  /// for permission or sets up an audio session; AppDelegate.swift does.
  static const MethodChannel _session = MethodChannel(
    'hu_accomponist/audio_session',
  );

  /// What start_recording returns when the library is not linked.
  static const int _notLinked = -1;

  int Function() _startRecording = _missing('start_recording');
  void Function() _stopRecording = _missingVoid('stop_recording');
  int Function() _recordingStatus = () => _notLinked;
  ffi.Pointer<ffi.Uint8> Function() _recordingMessage = () => ffi.nullptr;

  /// True only when every symbol resolved. Callers can use it to explain
  /// the situation rather than silently recording nothing.
  bool isConnected = false;

  static int Function() _missing(String symbol) => () {
    debugPrint(
      '[Diagnostics] audio: $symbol unavailable — native library not '
      'linked into this build, so no audio is being captured.',
    );
    return _notLinked;
  };

  static void Function() _missingVoid(String symbol) =>
      () => _missing(symbol)();

  void _init() {
    try {
      final library = ffi.DynamicLibrary.process();
      _startRecording = library
          .lookup<ffi.NativeFunction<ffi.Int32 Function()>>('start_recording')
          .asFunction<int Function()>();
      _stopRecording = library
          .lookup<ffi.NativeFunction<ffi.Void Function()>>('stop_recording')
          .asFunction<void Function()>();
      _recordingStatus = library
          .lookup<ffi.NativeFunction<ffi.Int32 Function()>>('recording_status')
          .asFunction<int Function()>();
      _recordingMessage = library
          .lookup<ffi.NativeFunction<ffi.Pointer<ffi.Uint8> Function()>>(
            'recording_message',
          )
          .asFunction<ffi.Pointer<ffi.Uint8> Function()>();
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

  /// Asks for microphone permission (the system prompt appears the first
  /// time) and sets the audio session up for recording. Call it before
  /// anything else of a recording, so the prompt does not land in the middle
  /// of the count-in. Null means ready; otherwise a message for the player.
  Future<String?> prepare() async {
    if (!Platform.isIOS) return null;
    try {
      final result = await _session.invokeMethod<String>('prepare');
      if (result == 'granted') return null;
      return 'Microphone access is off for this app. Turn it on in '
          'Settings, under Hu Accomponist.';
    } on PlatformException catch (e) {
      return 'Could not set up audio recording: ${e.message}';
    } on MissingPluginException {
      // A build without the channel: nothing to prepare.
      return null;
    }
  }

  /// Opens the microphone. Null when it is recording; otherwise what to tell
  /// the player.
  String? begin() {
    debugPrint('[Diagnostics] audio: start_recording');
    final code = _startRecording();
    if (code == 0) return null;
    if (code == _notLinked) {
      return 'The audio engine is not available in this build.';
    }
    final problem = _describe(code);
    debugPrint('[Diagnostics] audio: could not start — $problem');
    return problem.message;
  }

  /// The latest problem since [begin], or null. Rust notices things a
  /// microphone does not announce: audio that is pure silence (permission
  /// denied), a stream that stopped delivering, processing that fell behind.
  AudioProblem? problem() {
    if (!isConnected) return null;
    final code = _recordingStatus();
    return code == 0 ? null : _describe(code);
  }

  void end() {
    debugPrint('[Diagnostics] audio: stop_recording');
    _stopRecording();
  }

  AudioProblem _describe(int code) {
    final native = _message();
    return AudioProblem(
      code,
      native.isNotEmpty ? native : 'Audio capture failed (code $code).',
    );
  }

  /// The C string behind recording_message. Bounded, in case it is not
  /// terminated.
  String _message() {
    final text = _recordingMessage();
    if (text == ffi.nullptr) return '';
    var length = 0;
    while (length < 255 && text[length] != 0) {
      length++;
    }
    return utf8.decode(text.asTypedList(length), allowMalformed: true);
  }
}
