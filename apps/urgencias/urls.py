from django.urls import path

from . import views

urlpatterns = [
    path("entregables/<int:pk>/urgencia/", views.activar, name="entregable_urgencia"),
    path("urgencias/<int:pk>/leer/", views.leer, name="urgencia_leer"),
    path("urgencias/<int:pk>/aceptar/", views.aceptar, name="urgencia_aceptar"),
]
