# hum: hum a tune, get a song

Brought over from the ECKO website's Flask backend, then grown. A user hums, the server finds the
notes, turns them into a song with one of three engines, and lets the user edit the band song by
typing or saying what they want ("softer drums", "make it jazz", "a different chorus").

## Layout

| Where | What |
| --- | --- |
| `views.py`, `views_raw.py`, `views_song.py`, `views_chat.py`, `urls.py` | The HTTP layer (Django). Everything under `/api/hum/`. |
| `transcription.py` | The hum as notes, kept two ways: `raw` exactly as hummed, and `quantized()` on the beat grid in the key. |
| `rawplay.py` | "Play back my hum": the raw notes on piano or synth, and as MIDI. |
| `song/` | The **band** engine: presets, chords, parts, the intro/verse/chorus/outro arranger, the song project model and the stem renderer. |
| `band.py` | The band engine as the views use it (where its files live, the notes graph). |
| `chat/` | The chat: Gemini turns words into edits (`commands.py`, `interpreter.py`), `executor.py` applies them to the song project, `turn.py` runs a whole turn. |
| `page_settings.py` | The app's song settings, translated for the epic engine. |
| `paths.py` | Where hums and songs are kept (`backend/hum_data/`, never served by URL). |
| `engine/audio/intake/` | Hum to notes: cleans the WAV and finds notes, tempo, key and tuning. |
| `engine/audio/arrange/`, `pipeline.py` | The **epic** engine: a full ensemble arranged around the tune. |
| `engine/accompanist/`, `engine/talk/song.py` | The **simple** engine: chords and a style around the tune. |
| `engine/talk/` | The simple engine's song maker and its settings, plus the API keys, ElevenLabs speech to text and text to speech, and the reply store the chat uses. |
| `tests/` | Pytest suites for the engines, and `test_api.py` for the HTTP layer. |

The engine code is plain Python with no web framework in it. Only the `views*.py` files, `band.py`
and `paths.py` know about Django.

## Setup

1. `pip install -r requirements.txt`, then `pip install --no-deps basic-pitch` (see the note in
   `requirements.txt`: its normal install would pull in TensorFlow, which isn't used).
2. FluidSynth, which turns MIDI into sound: `brew install fluid-synth`.
3. A General MIDI soundfont at `hum/engine/accompanist/soundfonts/FluidR3_GM.sf2` (148 MB, so it is
   git-ignored; copy it in by hand, or set `ECKO_SOUNDFONT`). Without it songs still render, but with
   the small retro Homebrew soundfont and they won't sound like instruments.
4. For the chat, put `GEMINI_API_KEY` and `ELEVENLABS_API_KEY` in `backend/.env` (see
   `.env.example`). Without them everything else works; chat replies say which key is missing, and
   without a working ElevenLabs key the app answers in text only.

## Endpoints

| Method & path | What it does |
| --- | --- |
| `POST /api/hum/upload` | Multipart `file` (.wav). Returns `filename` plus the tune found: `melody` (`hz` is a MIDI note, times in beats), `tempo`, `key`, `mode`, `warnings`. 400 with `{error, code}` when there's no usable tune (`silent`, `too_short`, `no_tune`...). |
| `POST /api/hum/song` | JSON `{hum, settings?, engine?}` returns the song as WAV. `hum` is the `filename` from upload; `engine` is `"band"` (default), `"epic"` or `"simple"`. |
| `POST /api/hum/notes` | The same body returns `{sung, played}` in seconds for drawing the notes (epic and simple add `contour`). |
| `GET /api/hum/engines` | The engines and the styles (and, for band, the moods) each knows. |
| `POST /api/hum/raw` | JSON `{hum}` returns the raw notes exactly as hummed (`midi, start, duration, velocity`, seconds from the first note), the `quantized` copy (beats, in the key), `tempo`, `key`, `mode`, `tuning_cents`, `duration`. |
| `POST /api/hum/raw/audio` | JSON `{hum, instrument?}` (`piano` or `synth`) returns the raw notes played as WAV. |
| `POST /api/hum/raw/midi` | JSON `{hum}` returns the raw notes as `hum.mid`. |
| `POST /api/hum/project` | JSON `{hum, settings?}` returns `{project}`: the band engine's song as an editable project (`song/project.py`). |
| `POST /api/hum/project/audio` | JSON `{project}` returns it mixed as WAV. Only tracks whose notes, instrument or tempo changed are rendered again (`X-Rendered-Tracks` names them). |
| `POST /api/hum/project/midi` | JSON `{project}` returns every track as `song.mid`. |
| `GET /api/hum/presets` | The band engine's genres (with each one's instruments) and moods. |
| `POST /api/hum/project/edit` | JSON `{project, edits}` applies edits without Gemini (the app's genre and mood chips). Returns `{project, changed, mixed, label, refused}`. |
| `POST /api/hum/project/notes` | JSON `{project}` returns `{sung, played}` for the graph of an edited song. |
| `POST /api/hum/chat` | JSON `{text, project, can_undo?, can_redo?}` (typed), or multipart `audio` + `state` (spoken). Returns `{heard, intent, reply, project, changed, mixed, label, error, speech_id}`; `project` is null when nothing changed. Undo and redo are the app's (it keeps the history). |
| `GET /api/hum/chat/speech/<speech_id>` | The reply spoken, streamed as MP3. |

`settings` (all optional): `emotion`, `speed`, `pitch` from 0 to 1 (0.5 keeps the hum as it was),
`style` (a genre word or null), `mood` (band only: `dark`, `chill`, `bright`, `hype`), `instruments` (a list of `{name, role: lead|background, level:
soft|normal|loud, section: all|start|end}`) and `energy` (`{start, end}`, -2 to 2). They choose how a
song is first made; after that, the band song is edited as a project (chat, chips, undo).

## The chat

Gemini gets a few lines about the song with every message (`chat/summary.py`) and must answer with
edits from a closed list (`chat/commands.py`): tempo, key, genre, mood, an instrument, a part's
volume, mute or solo, effects, adding or removing a part, a section played differently, a calmer or
bigger verse or chorus, undo and redo. A request that could mean two things gets one short question
back; one no edit can do gets an offer of what can. A rate limit is tried once more after a pause.
Mixer edits render nothing again; the others re-arrange from the hum and only re-render the parts
whose sound changed. The melody stays on top: no part is turned up past it.

## The engines

- **band** (default): a genre's small band (lofi is a Rhodes, a sub bass and soft swung drums) plays
  the tune as intro, verse, chorus and outro. Chords come from the detected key and fit the notes
  bar by bar; chords and pad sit below the tune and every stem is evened out before its volume, so
  the melody is always on top. Eight genres, four moods.
- **epic**: arranges a whole ensemble. Beautiful when the hum is clean; it asks more of the notes.
- **simple**: picks chords for the tune in a style. Steadier on a rough hum, plainer to listen to.

## Tests

```bash
python manage.py test hum        # the HTTP layer (the chat runs on fake Gemini and ElevenLabs)
python -m pytest                 # the engines
```

Four tests in `tests/audio/test_audio_fidelity.py` are marked as expected failures: the simple engine's
note detector (`extract_notes`) drops very short notes and merges repeated ones. They failed the same
way in the original ECKO project.
