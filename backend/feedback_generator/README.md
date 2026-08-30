# feedback_generator

Compares user's recorded phrase vs expected-performance notes. Generates
per-note immediate feedback + phrase summary + scores. Plain-Python package
(no Django app), wired via `api/views.py`'s `phrase_feedback_view`.

**Known limitation:** `dynamics` score always `null` — no velocity/loudness
data upstream (mobile app / `native_ffi`). Stub in `analysis.compute_dynamics_score`.

Pedal analysis not implemented — see `pedaling.py`.

## Testing

- Env: `DYLD_LIBRARY_PATH=/opt/homebrew/lib` (libvips not on default linker path, macOS)
- Unit + view tests:
  ```
  cd backend
  DYLD_LIBRARY_PATH=/opt/homebrew/lib python manage.py test feedback_generator.tests api.tests -v 2
  ```
- Manual smoke test:
  ```
  DYLD_LIBRARY_PATH=/opt/homebrew/lib python manage.py runserver
  curl -X POST http://127.0.0.1:8000/api/feedback/phrase -H "Content-Type: application/json" -d '{...}'
  ```
- Endpoint: `POST /api/feedback/phrase`
- Body: `phrase`, `timing.bpm`, `expected_notes[]`, `user_notes[]` (see `phrase_feedback_view` docstring for full schema)

Result:
{"phrase": 0, "immediate_feedback": [{"note_id": 1, "category": "pitch", "severity": "major", "message": "Wrong note \u2014 you played D5 instead of D#5.", "suggestion": "Practice this transition slowly and focus on the correct note.", "type": "immediate"}, {"note_id": 2, "category": "pitch", "severity": "major", "message": "Wrong note \u2014 you played C3 instead of G2.", "suggestion": "Practice this transition slowly and focus on the correct note.", "type": "immediate"}, {"note_id": 2, "category": "timing", "severity": "major", "message": "This note came in late, disrupting the rhythm.", "suggestion": "Practice this passage with a metronome, focusing on landing the note exactly on the beat.", "type": "immediate"}, {"note_id": 3, "category": "timing", "severity": "major", "message": "This note came in late, disrupting the rhythm.", "suggestion": "Practice this passage with a metronome, focusing on landing the note exactly on the beat.", "type": "immediate"}, {"note_id": 4, "category": "pitch", "severity": "major", "message": "Wrong note \u2014 you played D#3 instead of C3.", "suggestion": "Practice this transition slowly and focus on the correct note.", "type": "immediate"}, {"note_id": 4, "category": "duration", "severity": "major", "message": "This note was cut short compared to what's written.", "suggestion": "Slow down and count out this note's full written duration before returning to full tempo.", "type": "immediate"}, {"note_id": 5, "category": "missing_note", "severity": "major", "message": "This note was not played.", "suggestion": "Go through this passage slowly, note-by-note, to make sure this note is included.", "type": "immediate"}], "phrase_summary": {"phrase": 0, "scores": {"overall": 54, "pitch": 43, "rhythm": 64, "tempo": 58, "dynamics": null, "articulation": null}, "summary": "Pitch was inaccurate on 3 notes in this phrase.", "main_feedback": [{"category": "pitch", "severity": "major", "description": "Pitch was inaccurate on 3 notes in this phrase.", "practice_action": "Isolate the affected note(s) and check them against the expected pitch before playing the phrase at full tempo."}, {"category": "timing", "severity": "major", "description": "2 notes were noticeably early or late.", "practice_action": "Practice this phrase with a metronome, focusing on landing each note exactly on the beat."}, {"category": "missing_note", "severity": "major", "description": "One expected note was not played.", "practice_action": "Go through the phrase slowly note-by-note to make sure every note is played."}], "positive_feedback": [], "type": "phrase_summary"}}%   