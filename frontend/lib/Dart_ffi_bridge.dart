import 'dart:ffi' as ffi;

typedef NativeVoidFunction = ffi.Void Function();
typedef DartVoidFunction = void Function();

class AudioBridge {
  late final DartVoidFunction startRecording;
  late final DartVoidFunction stopRecording;

  AudioBridge() {
    final library = ffi.DynamicLibrary.process();

    startRecording = library
        .lookup<ffi.NativeFunction<NativeVoidFunction>>(
          'start_recording',
        )
        .asFunction();

    stopRecording = library
        .lookup<ffi.NativeFunction<NativeVoidFunction>>(
          'stop_recording',
        )
        .asFunction();
  }
}