from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.clientes.models import Cliente, Contrato
from apps.entregables.filtros import entero
from apps.entregables.htmx import con_vary, pide_parcial
from apps.entregables.visibilidad import entregables_visibles

from . import calidad as calidad_servicio
from . import tdr
from .models import ItemCalidad, ItemChecklistTDR


def _entregable(usuario, pk):
    """404 si el usuario no puede ver el entregable."""
    return get_object_or_404(entregables_visibles(usuario).select_related("contrato__cliente"), pk=pk)


def _errores(request, exc):
    messages.error(request, " ".join(exc.messages))


# ------------------------------------------------------------------ checklist por TDR (RF-44)

@login_required
@require_POST
def checklist_tdr(request, pk):
    """POST /entregables/<pk>/checklist/: generar desde el TDR, agregar un ítem o marcar el estado de uno."""
    e = _entregable(request.user, pk)
    if not tdr.puede_gestionar(request.user, e):
        raise PermissionDenied("Solo los responsables del entregable gestionan su checklist.")
    accion = request.POST.get("accion")
    try:
        if accion == "generar":
            creados = tdr.generar(e, request.user)
            messages.success(request, f"Se generaron {len(creados)} ítems desde la ficha del TDR." if creados
                             else "El checklist ya tenía todos los ítems de la ficha del TDR.")
        elif accion == "agregar":
            tdr.agregar(e, request.user, request.POST.get("texto"), request.POST.get("tipo"),
                        request.POST.get("obligatorio") == "on")
            messages.success(request, "Se agregó el ítem al checklist.")
        elif accion == "marcar":
            item_id = entero(request.POST.get("item"))
            if item_id is None:
                raise Http404("No existe ese ítem.")
            item = get_object_or_404(ItemChecklistTDR, pk=item_id, entregable=e)
            item.entregable = e
            tdr.marcar(item, request.user, request.POST.get("estado"), request.POST.get("adjunto") or None)
            messages.success(request, f"«{item.texto}» quedó «{item.get_estado_display()}».")
        else:
            raise ValidationError("Elija una acción válida sobre el checklist.")
    except ValidationError as exc:
        _errores(request, exc)
    return redirect(tdr.enlace(e))


@login_required
def checklists(request):
    """Pestaña «Checklists» de Entregables: consulta por cliente, contrato e ID-TDR sobre los entregables visibles."""
    qs = tdr.entregables_con_checklist(request.user)
    activos = {}
    cliente = entero(request.GET.get("cliente"))
    if cliente is not None:
        qs = qs.filter(contrato__cliente_id=cliente)
        activos["cliente"] = cliente
    contrato = entero(request.GET.get("contrato"))
    if contrato is not None:
        qs = qs.filter(contrato_id=contrato)
        activos["contrato"] = contrato
    id_tdr = (request.GET.get("id_tdr") or "").strip()[:50]
    if id_tdr:
        qs = qs.filter(id_tdr__icontains=id_tdr)
        activos["id_tdr"] = id_tdr
    qs = qs.order_by("contrato__cliente__nombre", "plazo", "id")

    visibles = entregables_visibles(request.user).filter(checklist_tdr__isnull=False).values("pk")
    opciones = {
        "clientes": Cliente.objects.filter(contratos__entregables__in=visibles).distinct().order_by("nombre"),
        "contratos": Contrato.objects.filter(entregables__in=visibles).select_related("cliente").distinct()
        .order_by("numero_contrato"),
    }
    nombres = {
        "cliente": {c.pk: c.nombre for c in opciones["clientes"]},
        "contrato": {c.pk: c.numero_contrato for c in opciones["contratos"]},
    }
    chips = []
    for clave, titulo in (("cliente", "Cliente"), ("contrato", "Contrato"), ("id_tdr", "ID-TDR")):
        if clave in activos:
            resto = request.GET.copy()
            resto.pop(clave, None)
            resto.pop("pagina", None)
            valor = activos[clave] if clave == "id_tdr" else nombres[clave].get(activos[clave], "no disponible")
            chips.append({"clave": clave, "texto": f"{titulo}: {valor}", "quitar": "?" + resto.urlencode()})

    paginador = Paginator(qs, 50)
    pagina = paginador.get_page(request.GET.get("pagina"))
    filas = list(pagina.object_list)
    for e in filas:
        e.porcentaje = round(100 * e.n_cumplidos / e.n_items) if e.n_items else 0
    resto = request.GET.copy()
    resto.pop("pagina", None)
    contexto = {
        "pagina": pagina, "filas": filas, "total": paginador.count, "opciones": opciones, "filtros_activos": activos,
        "n_filtros": len(activos), "chips": chips, "consulta_sin_pagina": resto.urlencode(), "pestana": "checklists",
    }
    if pide_parcial(request):
        return con_vary(render(request, "checklists/_checklists_lista.html", {**contexto, "es_htmx": True}))
    return con_vary(render(request, "checklists/checklists.html", contexto))


# ------------------------------------------------------------------ checklist de calidad (RF-45)

@login_required
@require_POST
def revision_calidad(request, pk):
    """POST /entregables/<pk>/calidad/: registra la revisión (r_<id> = CONFORME | NO_CONFORME, o_<id> = observación)."""
    e = _entregable(request.user, pk)
    if not calidad_servicio.puede_revisar(request.user, e):
        raise PermissionDenied("Solo el senior del entregable, el gerente o el admin registran la revisión de calidad.")
    respuestas = {
        item.pk: (request.POST.get(f"r_{item.pk}"), request.POST.get(f"o_{item.pk}", ""))
        for item in calidad_servicio.items_aplicables(e)
    }
    try:
        revision, devuelto = calidad_servicio.registrar(e, request.user, respuestas)
    except ValidationError as exc:
        _errores(request, exc)
    else:
        if revision.conforme and not devuelto:
            messages.success(request, "Revisión de calidad conforme: el entregable ya se puede aprobar.")
        elif devuelto:
            messages.success(request, "Revisión de calidad registrada con ítems no conformes: se generaron las "
                                      "observaciones, el entregable volvió a «En proceso» y se avisó al junior.")
        else:
            messages.success(request, "Revisión de calidad registrada.")
    return redirect(calidad_servicio.enlace(e))


@login_required
def calidad(request):
    """Configuración del checklist de calidad por cliente (gerente y admin; los seniors, sus clientes)."""
    usuario = request.user
    if not calidad_servicio.puede_ver_configuracion(usuario):
        raise PermissionDenied("La configuración del checklist de calidad es para seniors, gerente y admin.")
    clientes = list(calidad_servicio.clientes_configurables(usuario).order_by("nombre"))
    por_id = {c.pk: c for c in clientes}

    if request.method == "POST":
        item = None
        item_id = entero(request.POST.get("item"))
        if item_id is not None:
            item = get_object_or_404(ItemCalidad, pk=item_id)
        cliente = None
        cliente_id = entero(request.POST.get("cliente"))
        if item is None and cliente_id is not None:
            cliente = por_id.get(cliente_id)
            if cliente is None:
                raise PermissionDenied("No puede configurar el checklist de ese cliente.")
        try:
            guardado = calidad_servicio.guardar_item(
                usuario, item, cliente=cliente, texto=request.POST.get("texto"),
                categoria=request.POST.get("categoria"), obligatorio=request.POST.get("obligatorio") == "on",
                activo=request.POST.get("activo") == "on",
            )
        except ValidationError as exc:
            _errores(request, exc)
        else:
            messages.success(request, f"Se guardó el ítem «{guardado.texto}».")
        return redirect("calidad")

    editando = None
    editar_id = entero(request.GET.get("editar"))
    if editar_id is not None:
        editando = get_object_or_404(ItemCalidad, pk=editar_id)
        if not calidad_servicio.puede_configurar(usuario, editando.cliente):
            raise PermissionDenied("No puede editar ese ítem.")
    items = ItemCalidad.objects.select_related("cliente").order_by("orden", "id")
    grupos = [{"titulo": "Generales (aplican a todos los clientes)", "cliente": None,
               "items": [i for i in items if i.cliente_id is None], "editable": usuario.es_gerente_o_admin}]
    for c in clientes:
        grupos.append({"titulo": c.nombre, "cliente": c, "items": [i for i in items if i.cliente_id == c.pk],
                       "editable": True})
    return render(request, "checklists/calidad.html", {
        "entidad": "calidad", "grupos": grupos, "clientes": clientes, "categorias": ItemCalidad.Categoria.choices,
        "editando": editando, "puede_generales": usuario.es_gerente_o_admin,
    })
