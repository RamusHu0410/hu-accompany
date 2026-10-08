"""Talk mode's keys and model names, read from the environment (the app loads backend/.env)."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    gemini_api_key: str
    elevenlabs_api_key: str
    gemini_model: str
    gemini_thinking: str
    voice_id: str
    tts_model: str
    stt_model: str


def load_config() -> Config:
    env = os.environ.get
    return Config(
        gemini_api_key=env("GEMINI_API_KEY", "").strip(),
        elevenlabs_api_key=env("ELEVENLABS_API_KEY", "").strip(),
        gemini_model=env("GEMINI_MODEL", "gemini-3.1-flash-lite"),
        gemini_thinking=env("GEMINI_THINKING", "minimal"),
        voice_id=env("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb"),
        tts_model=env("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5"),
        stt_model=env("ELEVENLABS_STT_MODEL", "scribe_v2"),
    )
