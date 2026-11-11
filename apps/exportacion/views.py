"""Vista de exportación del entregable a PDF y Excel (SDD del Sprint 3, RF-47: HU-27, §10)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.entregables.visibilidad import entregables_visibles

from . import servicios


@login_required
@require_POST
def exportar(request, pk, formato):
    if formato not in servicios.FORMATOS:
        raise Http404("Formato de exportación desconocido.")
    entregable = get_object_or_404(
        entregables_visibles(request.user).select_related(
            "contrato__cliente", "contrato__linea_servicio", "plantilla__documento_formato", "junior_asignado",
            "senior_revisor",
        ),
        pk=pk,  # 404 si no lo ve
    )
    try:
        adjunto = servicios.exportar(entregable, request.user, formato)  # 403 si lo ve pero no puede exportar
    except servicios.FaltanDatos as error:
        messages.error(request, error.messages[0])
        return redirect(reverse("entregable_detalle", args=[entregable.pk]) + "#exportar")
    respuesta = FileResponse(
        adjunto.archivo.open("rb"), as_attachment=True, filename=adjunto.nombre_original,
        content_type=servicios.TIPOS_MIME[formato],
    )
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta
