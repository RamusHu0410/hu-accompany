"""Speaks a reply with ElevenLabs, streaming the MP3 so playback starts on the first chunk."""

from collections.abc import Iterator

from elevenlabs.client import ElevenLabs

AUDIO_FORMAT = "mp3_44100_128"
AUDIO_MIME = "audio/mpeg"


class Speaker:
    def __init__(self, api_key: str, voice_id: str, model: str, client=None):
        self._client = client or ElevenLabs(api_key=api_key)
        self._voice_id = voice_id
        self._model = model

    def stream(self, text: str, voice_id: str | None = None) -> Iterator[bytes]:
        """`voice_id` speaks with another voice (a gnome character's); None uses the configured one."""
        chunks = self._client.text_to_speech.stream(
            voice_id or self._voice_id,
            text=text,
            model_id=self._model,
            output_format=AUDIO_FORMAT,
        )
        return (chunk for chunk in chunks if chunk)
