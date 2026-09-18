"""Routes for the quiz package.

Mirrors api/urls.py's flat `path(...)` style. Include it from the project's
existing url conf with one line -- see quiz/README.md.
"""

from django.urls import path

from . import api

urlpatterns = [
    path("api/quiz/generate", api.generate_quiz_view),
    path("api/quiz/topics", api.quiz_topics_view),
]
