from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.clientes.models import Cliente
from apps.entregables.filtros import entero
from apps.entregables.visibilidad import entregables_visibles

from . import servicios
from .models import Penalidad


def _volver_al_entregable(pk):
    return redirect(reverse("entregable_detalle", args=[pk]) + "#penalidades")


@login_required
def penalidades(request):
    """Pestaña «Penalidades» de Entregables: lo incurrido en los entregables que la persona puede ver."""
    cliente_id = entero(request.GET.get("cliente"))
    contexto = servicios.listado_penalidades(request.user, cliente_id)
    contexto.update({"pestana": "penalidades", "cliente_id": cliente_id})
    return render(request, "cumplimiento/penalidades.html", contexto)


@login_required
@require_POST
def registrar_penalidad(request, pk):
    entregable = get_object_or_404(entregables_visibles(request.user).select_related("contrato"), pk=pk)
    try:
        servicios.registrar_penalidad(
            request.user, entregable, request.POST.get("motivo"), request.POST.get("monto"), request.POST.get("fecha"))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Se registró la penalidad.")
    return _volver_al_entregable(entregable.pk)


@login_required
@require_POST
def eliminar_penalidad(request, pk):
    penalidad = get_object_or_404(
        Penalidad.objects.filter(entregable__in=entregables_visibles(request.user)).select_related("entregable__contrato"),
        pk=pk)
    servicios.eliminar_penalidad(request.user, penalidad)
    messages.success(request, "Se eliminó la penalidad.")
    return _volver_al_entregable(penalidad.entregable_id)


@login_required
def vigencias(request):
    """Certificados y documentos del cliente con fecha de vencimiento (GET: lista; POST: registrar uno)."""
    gestionables = servicios.clientes_gestionables(request.user).order_by("nombre")
    if request.method == "POST":
        cliente = get_object_or_404(Cliente, pk=entero(request.POST.get("cliente")) or 0)
        try:
            doc = servicios.registrar_documento(
                request.user, cliente, request.POST.get("nombre"), request.POST.get("vence"), request.POST.get("notas"))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, f"Se registró «{doc.nombre}» de {cliente.nombre}.")
        return redirect("vigencias")
    documentos = servicios._anotar(list(servicios.documentos_visibles(request.user)))
    ids = set(gestionables.values_list("pk", flat=True))
    for d in documentos:
        d.editable = d.cliente_id in ids
    return render(request, "cumplimiento/vigencias.html", {
        "entidad": "vigencias", "documentos": documentos, "gestionables": gestionables,
        "preseleccionado": entero(request.GET.get("cliente")), "dias_aviso": settings.VIGENCIA_DIAS_AVISO,
    })


@login_required
@require_POST
def actualizar_vigencia(request, pk):
    documento = get_object_or_404(servicios.documentos_visibles(request.user), pk=pk)
    try:
        if request.POST.get("accion") == "retirar":
            servicios.retirar_documento(request.user, documento)
            messages.success(request, f"Se retiró «{documento.nombre}».")
        else:
            servicios.renovar_documento(request.user, documento, request.POST.get("vence"))
            messages.success(request, f"«{documento.nombre}» ahora vence el {documento.vence:%d/%m/%Y}.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("vigencias")
