"""HTTP layer for the quiz package.

Kept in the package rather than in api/views.py, following the same shape as
imslp_downloader/api.py, so the quiz feature is self-contained: the only
edit needed elsewhere is one line in api/urls.py wiring the route up.

This module does no quiz logic of its own -- it decodes the body, calls
generate_quiz, and translates the package's exceptions into status codes.
"""

import json

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .banks import bank_sizes
from .errors import InvalidQuizRequest, UnknownTopic
from .generator import DEFAULT_LENGTH, generate_quiz
from .topic import known_eras


@csrf_exempt
@require_http_methods(["POST"])
def generate_quiz_view(request: HttpRequest):
    """POST /api/quiz/generate -- build a music theory and history quiz for
    a typed topic heading.

    Body: {"topic": str (required, e.g. "RCM HISTORY 10 + ARCT CHEAT SHEET\\n
             The Middle Ages (ad 476 - ad 1450)"),
           "length": int (optional, default 15, clamped to 5-60),
           "seed": int (optional, makes the draw reproducible)}

    The topic line carries both the era and the level: naming ARCT unlocks
    the advanced slice of the bank, otherwise only History-10 core questions
    are drawn. Questions come back balanced across composers, forms,
    terminology and historical context.

    Response: QuizSet.as_dict() -- {"topic": {...}, "question_count": int,
    "questions": [{id, kind, category, prompt, choices, answer, accepted,
    explanation, level}, ...]}.

    Grading is done on the client: `answer` is the canonical correct answer
    and `accepted` every spelling a fill-in-the-blank should allow. This
    keeps the quiz playable with no round trip per question, at the cost of
    the answers being present in the payload -- fine for a practice tool,
    but it is the reason this is not an exam-proctoring endpoint.

    400 if `topic` is missing or blank, 404 if it names an era with no bank.
    """
    client_ip = request.META.get("REMOTE_ADDR")
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        print(f"[quiz] invalid JSON from {client_ip}")
        return JsonResponse({"error": "invalid JSON"}, status=400)

    topic = body.get("topic")
    length = body.get("length", DEFAULT_LENGTH)
    seed = body.get("seed")

    try:
        quiz = generate_quiz(topic, length=length, seed=seed)
    except InvalidQuizRequest as e:
        return JsonResponse({"error": str(e)}, status=400)
    except UnknownTopic as e:
        return JsonResponse(
            {"error": str(e), "eras": known_eras()},
            status=404,
        )
    except (TypeError, ValueError) as e:
        # A non-numeric `length` or `seed` is the caller's mistake, not a
        # server fault, so it is a 400 rather than a 500.
        return JsonResponse({"error": f"invalid parameter: {e}"}, status=400)
    except Exception as e:
        print(f"[quiz] error for {client_ip}: {e}")
        return JsonResponse({"error": str(e)}, status=500)

    print(
        f"[quiz] {client_ip} -> {quiz.era_key} "
        f"({quiz.level_label}), {len(quiz.questions)} question(s)"
    )
    return JsonResponse(quiz.as_dict())


@csrf_exempt
@require_http_methods(["GET"])
def quiz_topics_view(request: HttpRequest):
    """GET /api/quiz/topics -- the eras this build can generate quizzes for,
    with how many questions each bank holds. The app uses it to show topic
    suggestions before the student has typed anything."""
    sizes = bank_sizes()
    return JsonResponse(
        {
            "eras": [
                {"era_key": key, "era_name": name, "question_count": sizes.get(key, 0)}
                for key, name in known_eras().items()
            ]
        }
    )
