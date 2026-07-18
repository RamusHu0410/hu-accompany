from django.urls import path
from . import views

urlpatterns = [
    path("chat/", views.chat_view),
    path("api/search", views.search_view),
    path("api/imslp/search", views.imslp_search_view),
]
