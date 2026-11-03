from django.urls import path

from . import views

urlpatterns = [
    path("incorporacion/", views.incorporacion, name="incorporacion"),
    path("incorporacion/planes/", views.planes, name="incorporacion_planes"),
]
