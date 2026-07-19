from django.urls import path

from imslp_downloader import api as imslp_downloader_api

from . import views

urlpatterns = [
    path("chat/", views.chat_view),
    path("api/search", views.search_view),
    path("api/imslp/search", views.imslp_search_view),
    path("api/imslp/download", imslp_downloader_api.download_view),
]
