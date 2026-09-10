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

void start_recording(void) {
    fprintf(stderr, "[AudioBridge] start_recording called\n");
    listen_audio();
    fprintf(stderr, "[AudioBridge] listen_audio returned\n");
}

void stop_recording(void) {
    fprintf(stderr, "[AudioBridge] stop_recording called\n");
    stop_audio();
    fprintf(stderr, "[AudioBridge] stop_audio returned\n");
}