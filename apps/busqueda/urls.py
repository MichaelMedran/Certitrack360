from django.urls import path

from . import views

urlpatterns = [
    path("buscar/", views.vista_buscar, name="buscar"),
]
