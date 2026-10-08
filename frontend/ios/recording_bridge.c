//
//  recording_bridge.c
//  
//
//  Created by Kelvin Lau on 2026-06-27.
//
#include <stdio.h>
#include <stddef.h>
#include <stdint.h>

// Exported by libnative_ffi.a / libnative_ffi_sim.a (native_ffi/src/lib.rs).
extern int32_t listen_audio(void);
extern void stop_audio(void);
extern int32_t audio_status(void);
extern size_t audio_error_message(uint8_t *buf, size_t cap);

// Dart finds these by name at runtime (dart:ffi lookup in
// Audio_Native.dart); nothing in the compiled app calls them directly.
// Release builds hide C symbols by default, which made them impossible to
// look up, so they are marked visible explicitly. `used` keeps the linker
// from discarding them as unreferenced.
#define DART_EXPORT __attribute__((visibility("default"), used))

// 0 on success (also when already recording), else an error code; the codes
// are listed in native_ffi/src/audio.rs and mirrored in Audio_Native.dart.
DART_EXPORT int32_t start_recording(void) {
    int32_t status = listen_audio();
    fprintf(stderr, "[AudioBridge] start_recording -> %d\n", status);
    return status;
}

DART_EXPORT void stop_recording(void) {
    stop_audio();
    fprintf(stderr, "[AudioBridge] stop_recording\n");
}

// 0, a warning (100 and up: audio still analysed) or an error code, from
// anything that went wrong since the recording started.
DART_EXPORT int32_t recording_status(void) {
    return audio_status();
}

// The message belonging to recording_status, as a NUL-terminated UTF-8
// string in a buffer owned by this file: read it before the next call.
// Dart's calls come one at a time from its UI isolate, so one buffer is enough.
DART_EXPORT const char *recording_message(void) {
    static uint8_t buffer[256];
    audio_error_message(buffer, sizeof buffer);
    return (const char *)buffer;
}
