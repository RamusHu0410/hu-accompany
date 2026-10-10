"""The chat's services, built from the same keys and models as talk mode (hum/engine/talk/config.py).
A missing key gives a plain message when it's used, not a crash at startup."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from hum.engine.talk.config import Config
from hum.engine.talk.store import ShortTermStore
from hum.engine.talk.stt import Transcriber
from hum.engine.talk.tts import Speaker

from .interpreter import ChatInterpreter
from .turn import ChatPipeline, MissingKey


@dataclass
class ChatServices:
    pipeline: ChatPipeline
    speak: Callable[[str], Iterable[bytes]]
    replies: ShortTermStore  # reply texts waiting to be spoken, by id


def build_chat_services(config: Config) -> ChatServices:
    if config.gemini_api_key:
        understand = ChatInterpreter(config.gemini_api_key, config.gemini_model, config.gemini_thinking).understand
    else:
        understand = _missing("GEMINI_API_KEY")
    if config.elevenlabs_api_key:
        transcribe = Transcriber(config.elevenlabs_api_key, config.stt_model).transcribe
        speaker = Speaker(config.elevenlabs_api_key, config.voice_id, config.tts_model)
        speak = speaker.stream
    else:
        transcribe = speak = _missing("ELEVENLABS_API_KEY")
    return ChatServices(ChatPipeline(understand, transcribe), speak, ShortTermStore(keep_at_most=200))


def _missing(key_name: str):
    def fail(*_args):
        raise MissingKey(f"{key_name} is missing. Add it to backend/.env and restart the server.")

    return fail
