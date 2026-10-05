from django.urls import path

from . import views

urlpatterns = [path("asistente/", views.asistente, name="asistente")]
