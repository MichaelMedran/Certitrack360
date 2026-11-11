from django.urls import path

from . import views

urlpatterns = [
    path("etiquetas/", views.etiquetas, name="etiquetas"),
]
