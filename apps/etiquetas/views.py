"""Pantallas de etiquetas (SDD del Sprint 3, RF-41, §7.2 y §10)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.alertas.enlaces import es_enlace_interno
from apps.entregables.filtros import entero
from apps.entregables.visibilidad import entregables_visibles

from . import servicios
from .forms import EtiquetaForm
from .models import Etiqueta


def _exigir_crear(request):
    servicios.exigir(servicios.puede_crear(request.user))


def _destino(request, por_defecto):
    """A dónde volver tras crear una etiqueta desde «Nuevo entregable» o el detalle: solo rutas internas."""
    volver = request.POST.get("volver", "")
    return volver if es_enlace_interno(volver) else por_defecto


@login_required
def etiquetas(request):
    """GET /etiquetas/: catálogo. Senior, gerente y admin (el junior recibe 403)."""
    _exigir_crear(request)
    catalogo = Etiqueta.objects.select_related("linea_servicio", "creada_por").annotate(
        n_contratos=Count("contratos", distinct=True), n_entregables=Count("entregables", distinct=True),
    ).order_by("nombre", "id")
    return render(request, "etiquetas/lista.html", {
        "entidad": "etiquetas", "etiquetas": catalogo, "puede_dar_de_baja": servicios.puede_dar_de_baja(request.user),
    })


@login_required
def etiqueta_nueva(request):
    """GET: formulario de alta. POST: crea la etiqueta (y, si viene `entregable`, se la asigna a quien puede)."""
    _exigir_crear(request)
    form = EtiquetaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            etiqueta = servicios.crear(request.user, form.cleaned_data["nombre"], form.cleaned_data["color"])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            mensaje = f"Se creó la etiqueta «{etiqueta.nombre}»."
            entregable_id = entero(request.POST.get("entregable"))
            if entregable_id is not None:
                e = entregables_visibles(request.user).filter(pk=entregable_id).select_related("contrato").first()
                if e is not None and servicios.puede_asignar(request.user, e):
                    e.etiquetas_asignadas.add(etiqueta)
                    mensaje += " Quedó asignada al entregable."
            messages.success(request, mensaje)
            return redirect(_destino(request, "etiquetas"))
    if request.method == "POST" and not form.is_valid() and request.POST.get("volver"):
        # Alta rápida desde otra pantalla: se vuelve a ella con el motivo, no a un formulario aparte.
        messages.error(request, " ".join(m for errs in form.errors.values() for m in errs))
        return redirect(_destino(request, "etiquetas"))
    return render(request, "etiquetas/form.html", {"entidad": "etiquetas", "form": form, "etiqueta": None})


@login_required
def etiqueta_editar(request, pk):
    """GET: formulario de edición. POST: guarda nombre y color, o (gerente y admin) da de baja o reactiva."""
    _exigir_crear(request)
    etiqueta = get_object_or_404(Etiqueta, pk=pk)
    if request.method == "POST" and request.POST.get("accion") in ("baja", "alta"):
        servicios.cambiar_baja(request.user, etiqueta, request.POST["accion"] == "alta")
        messages.success(request, f"La etiqueta «{etiqueta.nombre}» " + ("se reactivó." if etiqueta.activa else "se dio de baja."))
        return redirect("etiquetas")
    form = EtiquetaForm(request.POST or None, instance=etiqueta)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Se guardaron los cambios de la etiqueta «{etiqueta.nombre}».")
        return redirect("etiquetas")
    return render(request, "etiquetas/form.html", {
        "entidad": "etiquetas", "form": form, "etiqueta": etiqueta, "puede_dar_de_baja": servicios.puede_dar_de_baja(request.user),
    })


@login_required
@require_POST
def asignar_etiquetas(request, pk):
    """POST /entregables/<pk>/etiquetas/: deja al entregable con las etiquetas marcadas (senior del entregable, gerente, admin)."""
    e = get_object_or_404(entregables_visibles(request.user).select_related("contrato"), pk=pk)  # 404 si no lo ve
    servicios.exigir(servicios.puede_asignar(request.user, e))  # lo ve pero no puede: 403
    ids = {entero(v) for v in request.POST.getlist("etiquetas")}
    ids.discard(None)
    elegidas = list(Etiqueta.objects.filter(pk__in=ids))
    try:
        if len(elegidas) != len(ids):
            raise ValidationError("Alguna etiqueta elegida no existe.")
        servicios.asignar(request.user, e, elegidas)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Se actualizaron las etiquetas del entregable.")
    return redirect("entregable_detalle", pk=e.pk)
