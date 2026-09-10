import 'dart:ffi' as ffi;
import 'package:flutter/foundation.dart';

class AudioNative {
  AudioNative._internal() {
    _init();
  }

  static final AudioNative _instance = AudioNative._internal();

  factory AudioNative() => _instance;

  late final void Function() startRecording;
  late final void Function() stopRecording;

  bool isConnected = false;

  void _init() {
    debugPrint('[AudioNative] Initializing FFI bridge...');

    try {
      final library = ffi.DynamicLibrary.process();

      debugPrint('[AudioNative] Looking up start_recording...');

      startRecording = library
          .lookup<ffi.NativeFunction<ffi.Void Function()>>(
            'start_recording',
          )
          .asFunction<void Function()>();

      debugPrint('[AudioNative] Looking up stop_recording...');

      stopRecording = library
          .lookup<ffi.NativeFunction<ffi.Void Function()>>(
            'stop_recording',
          )
          .asFunction<void Function()>();

      isConnected = true;
      debugPrint('[AudioNative] FFI bridge connected successfully.');
    } catch (error, stackTrace) {
      isConnected = false;
      debugPrint('[AudioNative] FFI bridge FAILED: $error');
      debugPrintStack(stackTrace: stackTrace);
      rethrow;
    }
  }

  void begin() {
    debugPrint('[AudioNative] Calling start_recording...');
    startRecording();
    debugPrint('[AudioNative] start_recording returned.');
  }

  void end() {
    debugPrint('[AudioNative] Calling stop_recording...');
    stopRecording();
    debugPrint('[AudioNative] stop_recording returned.');
  }
}