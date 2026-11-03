from django.urls import path

from . import views

urlpatterns = [
    path("repositorio/", views.repositorio, name="repositorio"),
    path("repositorio/nuevo/", views.nuevo, name="repositorio_nuevo"),
    path("repositorio/<int:pk>/", views.documento_detalle, name="repositorio_documento"),
    path("repositorio/versiones/<int:pk>/descargar/", views.descargar_version, name="repositorio_descargar"),
]
