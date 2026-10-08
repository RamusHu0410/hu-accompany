from django.urls import path

from . import talk_views, views, views_raw

urlpatterns = [
    path("api/hum/upload", views.upload),
    path("api/hum/song", views.song),
    path("api/hum/notes", views.notes),
    path("api/hum/engines", views.engines),
    path("api/hum/raw", views_raw.raw_notes),
    path("api/hum/raw/audio", views_raw.raw_audio),
    path("api/hum/raw/midi", views_raw.raw_midi),
    path("api/hum/talk", talk_views.talk),
    path("api/hum/talk/speech/<str:reply_id>", talk_views.speech),
]
