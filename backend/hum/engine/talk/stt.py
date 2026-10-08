"""Turns a short recording into text with ElevenLabs Scribe (speech to text)."""

from elevenlabs.client import ElevenLabs


class Transcriber:
    def __init__(self, api_key: str, model: str, client=None):
        self._client = client or ElevenLabs(api_key=api_key)
        self._model = model

    def transcribe(self, audio: bytes, filename: str) -> str:
        """Any common format works (webm, m4a, mp4, wav, mp3). Returns '' for silence."""
        result = self._client.speech_to_text.convert(
            model_id=self._model,
            file=(filename, audio),
            tag_audio_events=False,  # no "(music)" or "(laughs)" in the text
        )
        return (result.text or "").strip()
