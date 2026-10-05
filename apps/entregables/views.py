import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.clientes.models import PlantillaTDR
from apps.cuentas.permisos import solo_senior_o_superior

from . import servicios
from .forms import EntregableForm, ObservacionForm, contratos_para
from .models import Entregable
from .visibilidad import entregables_visibles, es_senior_del_entregable


def _base(usuario):
    return entregables_visibles(usuario).select_related("contrato__cliente", "junior_asignado", "senior_revisor")


@login_required
def lista(request):
    qs = _base(request.user)
    estado = request.GET.get("estado", "")
    if estado in Entregable.Estado.values:
        qs = qs.filter(estado=estado)
    return render(request, "entregables/lista.html", {
        "entregables": qs, "estado": estado, "estados": Entregable.Estado.choices,
    })


@solo_senior_o_superior
def crear(request):
    usuario = request.user
    plantillas = PlantillaTDR.objects.select_related("cliente")
    plantilla = None
    pid = request.POST.get("plantilla") or request.GET.get("plantilla")
    if pid and pid.isdigit():
        plantilla = plantillas.filter(pk=pid).first()

    form = None
    if plantilla:
        if request.method == "POST":
            form = EntregableForm(usuario, plantilla, request.POST)
            if form.is_valid():
                entregable = form.guardar(usuario)
                servicios.registrar_creacion(entregable, usuario)
                messages.success(request, "El entregable se creó y se asignó al junior.")
                return redirect("entregable_detalle", pk=entregable.pk)
        else:
            form = EntregableForm(usuario, plantilla)
    elif request.method == "POST":
        messages.error(request, "Primero elija una plantilla de TDR.")
    return render(request, "entregables/crear.html", {
        "plantillas": plantillas, "plantilla": plantilla, "form": form,
        "hay_contratos": contratos_para(usuario).exists(),
    })


@login_required
def detalle(request, pk):
    entregable = get_object_or_404(_base(request.user), pk=pk)  # 404 si no es visible
    return render(request, "entregables/detalle.html", _contexto_detalle(request.user, entregable))


def _contexto_detalle(usuario, e):
    es_senior = es_senior_del_entregable(usuario, e)
    return {
        "e": e, "es_senior": es_senior,
        "observaciones": e.observaciones.select_related("autor"),
        "historial": e.historial.select_related("usuario"),
        "form_obs": ObservacionForm(),
        "siguientes": [
            (dest, Entregable.Estado(dest).label)
            for (orig, dest), quien in servicios.TRANSICIONES.items()
            if orig == e.estado and (es_senior or (quien == "junior" and usuario.pk == e.junior_asignado_id))
        ],
    }


@login_required
@require_POST
def cambiar_estado(request, pk):
    """Transición desde el detalle (formulario clásico)."""
    e = get_object_or_404(_base(request.user), pk=pk)
    nuevo = request.POST.get("estado", "")
    try:
        servicios.mover(
            e, nuevo, request.user,
            tipo_error=request.POST.get("tipo_error"), descripcion=request.POST.get("descripcion", ""),
        )
        messages.success(request, f"El entregable pasó a «{e.get_estado_display()}».")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    except PermissionDenied as exc:
        messages.error(request, str(exc) or "No tiene permiso para esa acción.")
    return redirect("entregable_detalle", pk=e.pk)


@login_required
@require_POST
def mover_api(request, pk):
    """Endpoint del tablero (arrastrar y soltar). Responde JSON; el cliente revierte si hay error."""
    e = get_object_or_404(_base(request.user), pk=pk)
    try:
        payload = json.loads(request.body or "{}")
    except ValueError:
        return JsonResponse({"ok": False, "error": "Solicitud no válida."}, status=400)
    try:
        servicios.mover(
            e, payload.get("estado", ""), request.user,
            tipo_error=payload.get("tipo_error"), descripcion=payload.get("descripcion", ""),
        )
    except ValidationError as exc:
        return JsonResponse({"ok": False, "error": " ".join(exc.messages), "pide_observacion": "observación" in " ".join(exc.messages) or "tipo de error" in " ".join(exc.messages)}, status=400)
    except PermissionDenied as exc:
        return JsonResponse({"ok": False, "error": str(exc) or "No tiene permiso."}, status=403)
    return JsonResponse({"ok": True, "estado": e.estado})


@login_required
def tablero(request):
    qs = _base(request.user)
    columnas = []
    for valor, etiqueta in Entregable.Estado.choices:
        columnas.append({"valor": valor, "etiqueta": etiqueta, "tarjetas": [e for e in qs if e.estado == valor]})
    return render(request, "entregables/tablero.html", {"columnas": columnas, "hoy": timezone.localdate()})


@login_required
@require_POST
def registrar_observacion(request, pk):
    e = get_object_or_404(_base(request.user), pk=pk)
    if not es_senior_del_entregable(request.user, e):
        raise PermissionDenied
    form = ObservacionForm(request.POST)
    if form.is_valid():
        from apps.alertas.models import Notificacion
        from .models import Observacion

        Observacion.objects.create(
            entregable=e, autor=request.user, tipo_error=form.cleaned_data["tipo_error"],
            descripcion=form.cleaned_data["descripcion"],
        )
        Notificacion.objects.create(
            usuario=e.junior_asignado, entregable=e, tipo=Notificacion.Tipo.OBSERVACION,
            mensaje=f"Nueva observación en «{e.titulo}».",
        )
        messages.success(request, "Observación registrada.")
    else:
        messages.error(request, "Complete el tipo de error y la descripción de la observación.")
    return redirect("entregable_detalle", pk=e.pk)


@login_required
@require_POST
def resolver_observacion(request, pk, obs_id):
    e = get_object_or_404(_base(request.user), pk=pk)
    obs = get_object_or_404(e.observaciones, pk=obs_id)
    if not es_senior_del_entregable(request.user, e):
        raise PermissionDenied
    solucion = request.POST.get("solucion", "").strip()
    if not solucion:
        messages.error(request, "Escriba la solución aplicada para marcar la observación como resuelta.")
    else:
        obs.solucion, obs.resuelta = solucion, True
        obs.save(update_fields=["solucion", "resuelta"])
        messages.success(request, "Observación resuelta.")
    return redirect("entregable_detalle", pk=e.pk)
