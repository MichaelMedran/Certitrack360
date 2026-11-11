"""Acciones de la alerta urgente (SDD del Sprint 3, RF-43, §7.4 y §10). Todas son POST y vuelven a la pantalla de origen."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.alertas.enlaces import es_enlace_interno
from apps.entregables.visibilidad import entregables_visibles

from . import servicios
from .forms import ActivarAlertaForm
from .models import AlertaUrgente


def _volver(request, alerta, por_defecto=None):
    """A dónde volver: la pantalla de origen (solo rutas internas), el entregable si lo ve, o el inicio."""
    destino = request.POST.get("volver", "")
    if es_enlace_interno(destino):
        return destino
    if por_defecto:
        return por_defecto
    if entregables_visibles(request.user).filter(pk=alerta.entregable_id).exists():
        return servicios.enlace_detalle(alerta)
    return "/"


def _alerta_para_responder(request, pk):
    alerta = get_object_or_404(AlertaUrgente.objects.select_related("entregable__contrato__cliente"), pk=pk)
    if not servicios.puede_responder(request.user, alerta):
        # Lo que no ve responde 404; lo que ve pero no puede hacer, 403.
        if entregables_visibles(request.user).filter(pk=alerta.entregable_id).exists():
            raise PermissionDenied("No tiene permiso para responder esta alerta.")
        raise Http404
    return alerta


@login_required
@require_POST
def activar(request, pk):
    """POST /entregables/<pk>/urgencia/: activa la alerta (senior del entregable, gerente, admin)."""
    e = get_object_or_404(entregables_visibles(request.user).select_related("contrato__cliente"), pk=pk)  # 404 si no lo ve
    servicios.exigir(servicios.puede_activar(request.user, e))  # lo ve pero no puede: 403
    form = ActivarAlertaForm(request.POST)
    try:
        if not form.is_valid():
            raise ValidationError([m for errs in form.errors.values() for m in errs])
        servicios.activar(request.user, e, form.cleaned_data["naturaleza"], form.cleaned_data["plazo_esperado"])
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "La alerta urgente quedó activa y se avisó a la guardia y a los responsables.")
    return redirect(reverse("entregable_detalle", args=[e.pk]) + "#urgencia")


@login_required
@require_POST
def leer(request, pk):
    """POST /urgencias/<pk>/leer/: confirma la lectura (queda quién y cuándo)."""
    alerta = _alerta_para_responder(request, pk)
    servicios.confirmar_lectura(request.user, alerta)
    messages.success(request, "Se registró su confirmación de lectura.")
    return redirect(_volver(request, alerta))


@login_required
@require_POST
def aceptar(request, pk):
    """POST /urgencias/<pk>/aceptar/: acepta el caso (una sola persona) y cierra la alerta."""
    alerta = _alerta_para_responder(request, pk)
    try:
        servicios.aceptar(request.user, alerta)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Aceptó el caso: quedó registrado como quien atiende la contingencia.")
    return redirect(_volver(request, alerta))
