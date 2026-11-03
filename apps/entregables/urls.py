from django.urls import path

from . import views

urlpatterns = [
    path("entregables/", views.lista, name="entregables"),
    path("entregables/nuevo/", views.crear, name="entregable_nuevo"),
    path("entregables/<int:pk>/", views.detalle, name="entregable_detalle"),
    path("entregables/<int:pk>/mover/", views.cambiar_estado, name="entregable_estado"),
    path("entregables/<int:pk>/responsables/", views.gestionar_responsables, name="entregable_responsables"),
    path("entregables/<int:pk>/tiempo/", views.gestionar_tiempo, name="entregable_tiempo"),
    path("tiempos/", views.historial_tiempos, name="tiempos"),
    path("entregables/<int:pk>/observaciones/", views.registrar_observacion, name="observacion_nueva"),
    path("observaciones/<int:obs_id>/resolver/", views.resolver_observacion, name="observacion_resolver"),
    # Sprint 2 (RF-25 a RF-27)
    path("observaciones/", views.historial_observaciones, name="observaciones"),
    path("observaciones/<int:obs_id>/corregir/", views.corregir_observacion, name="observacion_corregir"),
    path("observaciones/<int:obs_id>/revisar/", views.revisar_observacion, name="observacion_revisar"),
    path("entregables/<int:pk>/adjuntos/", views.adjunto_subir, name="adjunto_subir"),
    path("adjuntos/<int:adjunto_id>/descargar/", views.adjunto_descargar, name="adjunto_descargar"),
    path("adjuntos/<int:adjunto_id>/eliminar/", views.adjunto_eliminar, name="adjunto_eliminar"),
    # Sprint 2 (RF-28 y RF-29)
    path("adjuntos/<int:adjunto_id>/restaurar/", views.adjunto_restaurar, name="adjunto_restaurar"),
    path("entregables/<int:pk>/entregar/", views.entregar, name="entregable_entregar"),
    path("entregas/", views.historial_entregas, name="entregas"),
    path("entregas/<int:entrega_id>/acta/", views.entrega_acta, name="entrega_acta"),
    path("tablero/", views.tablero, name="tablero"),
]
