from django.urls import path

from . import views

urlpatterns = [
    path("api/scores/search", views.search_view),
    path("api/scores/<int:score_id>/musicxml", views.musicxml_view),
]
