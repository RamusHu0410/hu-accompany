# hum: hum a tune, get a song

Brought over from the ECKO website's Flask backend. A user hums, the server finds the notes, turns
them into a song with one of two engines, and lets the user reshape it by typing or saying what they
want ("make it faster", "add a violin").

## Layout

| Where | What |
| --- | --- |
| `views.py`, `talk_views.py`, `urls.py` | The HTTP layer (Django). Everything under `/api/hum/`. |
| `page_settings.py` | The app's song settings, translated for the epic engine. |
| `paths.py` | Where hums and songs are kept (`backend/hum_data/`, never served by URL). |
| `engine/audio/intake/` | Hum to notes: cleans the WAV and finds notes, tempo, key and tuning. |
| `engine/audio/arrange/`, `pipeline.py` | The **epic** engine: a full ensemble arranged around the tune. |
| `engine/accompanist/`, `engine/talk/song.py` | The **simple** engine: chords and a style around the tune. |
| `engine/talk/` | Talk mode: Gemini works out what was asked, ElevenLabs hears and speaks it. |
| `tests/` | Pytest suites for the engines, and `test_api.py` for the HTTP layer. |

The engine code is plain Python with no web framework in it. Only `views.py` and `talk_views.py`
know about Django.

## Setup

1. `pip install -r requirements.txt`, then `pip install --no-deps basic-pitch` (see the note in
   `requirements.txt`: its normal install would pull in TensorFlow, which isn't used).
2. FluidSynth, which turns MIDI into sound: `brew install fluid-synth`.
3. A General MIDI soundfont at `hum/engine/accompanist/soundfonts/FluidR3_GM.sf2` (148 MB, so it is
   git-ignored; copy it in by hand, or set `SOUNDFONT_PATH`). Without it songs still render, but with
   the small retro Homebrew soundfont and they won't sound like instruments.
4. For talk mode, put `GEMINI_API_KEY` and `ELEVENLABS_API_KEY` in `backend/.env` (see
   `.env.example`). Without them everything else works; talk replies say which key is missing.

## Endpoints

| Method & path | What it does |
| --- | --- |
| `POST /api/hum/upload` | Multipart `file` (.wav). Returns `filename` plus the tune found: `melody` (`hz` is a MIDI note, times in beats), `tempo`, `key`, `mode`, `warnings`. 400 with `{error, code}` when there's no usable tune (`silent`, `too_short`, `no_tune`...). |
| `POST /api/hum/song` | JSON `{hum, settings?, engine?}` returns the song as WAV. `hum` is the `filename` from upload; `engine` is `"epic"` (default) or `"simple"`. |
| `POST /api/hum/notes` | The same body returns `{sung, played, contour}` (seconds on the hum's time axis), for drawing the notes. |
| `GET /api/hum/engines` | The engines and the styles each knows. |
| `POST /api/hum/talk` | JSON `{text, settings?, previous?, character?}` (typed), or multipart `audio` + `state` (spoken). Returns `{heard, intent, settings, changed, understood, reply, error, speech_id}`. |
| `GET /api/hum/talk/speech/<speech_id>` | The reply spoken, streamed as MP3. |

`settings` (all optional): `emotion`, `speed`, `pitch` from 0 to 1 (0.5 keeps the hum as it was),
`style` (a genre word or null), `instruments` (a list of `{name, role: lead|background, level:
soft|normal|loud, section: all|start|end}`) and `energy` (`{start, end}`, -2 to 2). Talk mode changes
these, and the app sends the result back with the next song request.

## The two engines

- **epic**: arranges a whole ensemble. Beautiful when the hum is clean; it asks more of the notes.
- **simple**: picks chords for the tune in a style. Steadier on a rough hum, plainer to listen to.

## Tests

```bash
python manage.py test hum        # the HTTP layer (talk mode runs on fake Gemini and ElevenLabs)
python -m pytest                 # the engines
```

Four tests in `tests/audio/test_audio_fidelity.py` are marked as expected failures: the simple engine's
note detector (`extract_notes`) drops very short notes and merges repeated ones. They failed the same
way in the original ECKO project.
