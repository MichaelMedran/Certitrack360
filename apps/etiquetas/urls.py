from django.urls import path

from . import views

urlpatterns = [
    path("etiquetas/", views.etiquetas, name="etiquetas"),
    path("etiquetas/nueva/", views.etiqueta_nueva, name="etiqueta_nueva"),
    path("etiquetas/<int:pk>/", views.etiqueta_editar, name="etiqueta_editar"),
    path("entregables/<int:pk>/etiquetas/", views.asignar_etiquetas, name="entregable_etiquetas"),
]
