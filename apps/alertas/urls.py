from django.urls import path

from . import views

urlpatterns = [
    path("notificaciones/", views.lista, name="notificaciones"),
    path("notificaciones/leidas/", views.marcar_leidas, name="notificaciones_leidas"),
]
