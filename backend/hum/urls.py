from django.urls import path

from . import views, views_chat, views_raw, views_song

urlpatterns = [
    path("api/hum/upload", views.upload),
    path("api/hum/song", views.song),
    path("api/hum/notes", views.notes),
    path("api/hum/engines", views.engines),
    path("api/hum/raw", views_raw.raw_notes),
    path("api/hum/raw/audio", views_raw.raw_audio),
    path("api/hum/raw/midi", views_raw.raw_midi),
    path("api/hum/project", views_song.project),
    path("api/hum/project/audio", views_song.project_audio),
    path("api/hum/project/midi", views_song.project_midi),
    path("api/hum/project/edit", views_chat.edit),
    path("api/hum/project/notes", views_chat.notes),
    path("api/hum/presets", views_song.presets),
    path("api/hum/chat", views_chat.chat),
    path("api/hum/chat/speech/<str:reply_id>", views_chat.speech),
]
