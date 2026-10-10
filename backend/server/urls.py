#from django.urls import path, include

#urlpatterns = [
#    path("", include("api.urls")),
#]
from django.urls import path, include
from django.conf import settings
from django.urls import re_path
from server import views

urlpatterns = [
    path("", include("api.urls")),
    path("", include("scores.urls")),
    path("", include("hum.urls")),
    re_path(r'^storage/(?P<path>.*)$', views.storage),
]