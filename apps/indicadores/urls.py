from django.urls import path

from . import views

urlpatterns = [
    path("indicadores/", views.indicadores, name="indicadores"),
]
