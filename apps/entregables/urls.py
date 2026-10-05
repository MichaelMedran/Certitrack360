from django.urls import path

from . import views

urlpatterns = [
    path("entregables/", views.lista, name="entregables"),
    path("entregables/nuevo/", views.crear, name="entregable_nuevo"),
    path("entregables/<int:pk>/", views.detalle, name="entregable_detalle"),
    path("entregables/<int:pk>/estado/", views.cambiar_estado, name="entregable_estado"),
    path("entregables/<int:pk>/observaciones/", views.registrar_observacion, name="observacion_nueva"),
    path("entregables/<int:pk>/observaciones/<int:obs_id>/resolver/", views.resolver_observacion, name="observacion_resolver"),
    path("entregables/<int:pk>/adjuntos/", views.adjunto_subir, name="adjunto_subir"),
    path("adjuntos/<int:adjunto_id>/descargar/", views.adjunto_descargar, name="adjunto_descargar"),
    path("adjuntos/<int:adjunto_id>/eliminar/", views.adjunto_eliminar, name="adjunto_eliminar"),
    path("tablero/", views.tablero, name="tablero"),
    path("tablero/mover/<int:pk>/", views.mover_api, name="tablero_mover"),
]
