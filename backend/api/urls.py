from django.urls import include, path

from . import views

urlpatterns = [
    path("developer/chat/", views.chat_view),
    path("api/feedback/phrase", views.phrase_feedback_view),
    path("api/feedback/summary", views.summary_feedback_view),
    path("", include("quiz.urls")),
]
