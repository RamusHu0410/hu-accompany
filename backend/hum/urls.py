from django.urls import path

from . import talk_views, views

urlpatterns = [
    path("api/hum/upload", views.upload),
    path("api/hum/song", views.song),
    path("api/hum/notes", views.notes),
    path("api/hum/engines", views.engines),
    path("api/hum/talk", talk_views.talk),
    path("api/hum/talk/speech/<str:reply_id>", talk_views.speech),
]
