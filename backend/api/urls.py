from django.urls import path
from . import views

urlpatterns = [
    path("chat/", views.chat_view),
    path("api/search", views.search_view),
]
