//
//  recording_bridge.c
//  
//
//  Created by Kelvin Lau on 2026-06-27.
//
#include <stdio.h>

#include <stdio.h>

extern void listen_audio(void);
extern void stop_audio(void);

// Dart finds these two by name at runtime (dart:ffi lookup in
// Audio_Native.dart); nothing in the compiled app calls them directly.
// Release builds hide C symbols by default, which made them impossible to
// look up, so they are marked visible explicitly. `used` keeps the linker
// from discarding them as unreferenced.
#define DART_EXPORT __attribute__((visibility("default"), used))

DART_EXPORT void start_recording(void) {
    fprintf(stderr, "[AudioBridge] start_recording called\n");
    listen_audio();
    fprintf(stderr, "[AudioBridge] listen_audio returned\n");
}

DART_EXPORT void stop_recording(void) {
    fprintf(stderr, "[AudioBridge] stop_recording called\n");
    stop_audio();
    fprintf(stderr, "[AudioBridge] stop_audio returned\n");
}