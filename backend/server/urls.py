#from django.urls import path, include

#urlpatterns = [
#    path("", include("api.urls")),
#]
from django.urls import path, include
from django.conf import settings
from django.urls import re_path
from django.views.static import serve

urlpatterns = [
    path("", include("api.urls")),
    re_path(r'^storage/(?P<path>.*)$', serve, {
        'document_root': settings.BASE_DIR / 'storage',
    }),
]