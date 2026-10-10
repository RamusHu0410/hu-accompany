"""Stand-ins for Gemini and ElevenLabs, so the chat tests never touch the network."""

from types import SimpleNamespace

from hum.chat.commands import Answer, Edit
from hum.chat.services import ChatServices
from hum.chat.turn import ChatPipeline
from hum.engine.talk.store import ShortTermStore

QUIETER_DRUMS = Answer(intent="edit", edits=[Edit(action="change_volume", part="drums", direction="down")],
                       language="English", reply="Drums are softer now.")


class FakeGemini:
    """Answers with the prepared Answer (or raises) and remembers what it was asked."""

    def __init__(self, answer: Answer = QUIETER_DRUMS, error: Exception | None = None):
        self.answer, self.error = answer, error
        self.calls = []

    def __call__(self, text, project):
        self.calls.append((text, project))
        if self.error:
            raise self.error
        return self.answer


class FakeEars:
    def __init__(self, words: str = "softer drums please", error: Exception | None = None):
        self.words, self.error = words, error
        self.calls = []

    def __call__(self, audio, filename):
        self.calls.append((audio, filename))
        if self.error:
            raise self.error
        return self.words


def fake_voice(_text):
    yield b"ID3-first-chunk"
    yield b"-rest-of-the-mp3"


def fake_chat_services(gemini=None, ears=None, speak=fake_voice) -> ChatServices:
    return ChatServices(ChatPipeline(gemini or FakeGemini(), ears or FakeEars()), speak, ShortTermStore(keep_at_most=10))


class FakeGenaiClient:
    """The google-genai client's models.generate_content, answering from a script of replies:
    each is the JSON text to return, or an exception to raise."""

    def __init__(self, *script):
        self.script = list(script)
        self.prompts = []
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, model, contents, config):
        self.prompts.append(contents)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return SimpleNamespace(text=step)
