# quiz

Generates music theory and history quizzes from a typed topic heading, of
the kind an RCM student already has at the top of their cheat sheet:

```
RCM HISTORY 10 + ARCT CHEAT SHEET
The Middle Ages (ad 476 - ad 1450)
```

Both lines are optional and order does not matter. The era is matched by
name or alias; naming **ARCT** anywhere unlocks the advanced slice of the
bank, otherwise only History-10 core questions are drawn.

## Wiring it up

**This is the one edit outside `quiz/`.** The package ships complete but
Django has no URL auto-discovery, so the route has to be included from an
existing url conf. Add one line to `api/urls.py`:

```python
urlpatterns = [
    ...
    path("", include("quiz.urls")),   # <- add this (and `include` to the django.urls import)
]
```

Until that line exists, `/api/quiz/generate` returns 404. Nothing else in
the project needs to change — there are no models, no migrations and no
`INSTALLED_APPS` entry, because the package stores nothing.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/quiz/generate` | Build a quiz for a topic |
| `GET` | `/api/quiz/topics` | List covered eras and bank sizes |

```jsonc
// POST /api/quiz/generate
{ "topic": "RCM HISTORY 10 + ARCT CHEAT SHEET\nThe Middle Ages (ad 476 - ad 1450)",
  "length": 20,      // optional, default 15, clamped 5-60
  "seed": 1 }        // optional, reproducible draw
```

400 if `topic` is missing or blank; 404 (with the covered `eras`) if it
names an era with no bank.

## Layout

```
models.py     Question / QuizSet dataclasses, framework-free
topic.py      parses the heading -> era + level
banks/        one module per era, hand-written questions
generator.py  category-balanced draw
api.py        Django views (the only Django-aware module)
urls.py       routes
```

`models.py`, `topic.py`, `banks/` and `generator.py` import no Django, for
the same reason `feedback_generator/judges` does not: the content and the
selection logic should not depend on how the API serializes them.

## Why the banks are hand-written

This is exam-prep content. A generated question with a plausible but wrong
date or a misattributed composer teaches the student something false, which
is worse than having no question. The banks are therefore written and
reviewable, and `_builders.mc()` asserts at import that every
multiple-choice answer actually appears among its own choices — a typo in a
bank fails the process rather than silently shipping an unanswerable
question.

## Grading

Grading happens on the client: each question carries its `answer` and, for
fill-in-the-blanks, every `accepted` spelling. That keeps a quiz playable
with no round trip per question. It also means the answers are in the
payload, so this is a practice tool, not a proctored exam.

## Adding an era

1. Write `banks/<era>.py` with a module-level `QUESTIONS` list.
2. Register it in `banks/__init__.py`.
3. Add its name and aliases to `topic.ERA_ALIASES`.
