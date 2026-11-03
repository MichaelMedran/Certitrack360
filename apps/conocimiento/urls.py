from django.urls import path

from . import views

urlpatterns = [
    path("asistente/", views.asistente, name="asistente"),
    path("asistente/valorar/<int:pk>/", views.valorar, name="asistente_valorar"),
    path("procedimientos/", views.procedimientos, name="procedimientos"),
]
