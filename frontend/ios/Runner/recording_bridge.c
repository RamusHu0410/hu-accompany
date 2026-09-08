//
//  recording_bridge.c
//  
//
//  Created by Kelvin Lau on 2026-06-27.
//
#include <stdio.h>

// Exported by libnative_ffi_sim.a. Keeping this tiny C layer gives Dart
// stable C names while the audio implementation remains in Rust.
extern void listen_audio(void);
extern void stop_audio(void);

void start_recording(void) {
    listen_audio();
}

void stop_recording(void) {
    stop_audio();
}
