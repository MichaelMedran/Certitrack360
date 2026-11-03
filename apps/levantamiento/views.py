"""Vistas de las fichas de levantamiento del TDR (SDD del Sprint 2, RF-30: HU-14 y HU-06)."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.clientes.models import PlantillaTDR
from apps.cuentas.models import Usuario
from apps.entregables import archivos
from apps.entregables.filtros import entero
from apps.entregables.htmx import con_vary, pide_parcial
from apps.entregables.models import Entregable

from . import filtros, servicios
from .forms import FILA_ITEM_VACIA, EstadoDocumentalForm, FichaLevantamientoForm
from .models import ItemFicha
from .visibilidad import (
    contratos_para_ficha,
    fichas_visibles,
    puede_actualizar_documental,
    puede_confirmar,
    puede_editar_borrador,
)


def _base(usuario):
    return fichas_visibles(usuario).select_related(
        "contrato__cliente", "contrato__senior_responsable", "responsable", "creada_por", "confirmada_por"
    )


def _enriquecer_fila_item(fila, plantillas):
    datos = fila.get("datos") or {}
    plantilla_actual = str(fila.get("plantilla") or "")
    bloques = []
    for p in plantillas:
        pk_str = str(p.pk)
        campos = [
            {
                "nombre": c["nombre"],
                "etiqueta": c["etiqueta"],
                "tipo": c.get("tipo", "texto"),
                "opciones": c.get("opciones", []),
                "valor": str(datos.get(c["nombre"], "")),
            }
            for c in p.campos_requeridos
        ]
        bloques.append(
            {
                "pk": p.pk,
                "pk_str": pk_str,
                "Activa": plantilla_actual == pk_str,
                "campos": campos,
            }
        )
    return {**fila, "plantilla_str": plantilla_actual, "plantillas_con_valores": bloques}


def _contexto_editor(usuario, form):
    plantillas = list(PlantillaTDR.objects.select_related("cliente").all())
    form.filas = [_enriquecer_fila_item(f, plantillas) for f in form.filas]
    return {
        "form": form,
        "plantillas": plantillas,
        "frecuencias": ItemFicha.Frecuencia.choices,
        "juniors": list(Usuario.objects.filter(rol=Usuario.Rol.JUNIOR, is_active=True).order_by("first_name", "username")),
        "seniors": list(Usuario.objects.filter(rol=Usuario.Rol.SENIOR, is_active=True).order_by("first_name", "username")),
        "fila_item_vacia": _enriquecer_fila_item(dict(FILA_ITEM_VACIA), plantillas),
        "extensiones": ", ".join(archivos.extensiones_permitidas()),
        "tamano_max": f"{settings.MEDIA_MAX_UPLOAD_MB:g}",
    }


def _contexto_detalle(usuario, ficha, form_borrador=None, form_documental=None, vista_previa_datos=None, error_previa=None):
    items = list(ficha.items.select_related("plantilla", "junior", "senior").all())
    for it in items:
        it.ficha = ficha
        it.faltantes = it.datos_faltantes()
    entregables = (
        Entregable.objects.filter(items_ficha__ficha=ficha)
        .select_related("junior_asignado", "senior_revisor", "plantilla")
        .distinct()
        .order_by("plazo", "id")
    )
    edita_borrador = puede_editar_borrador(usuario, ficha)
    confirma = puede_confirmar(usuario, ficha)
    actualiza_doc = puede_actualizar_documental(usuario, ficha)

    contexto = {
        "entidad": "fichas",
        "ficha": ficha,
        "items": items,
        "entregables_generados": list(entregables),
        "puede_editar_borrador": edita_borrador,
        "puede_confirmar": confirma,
        "puede_pedir_confirmacion": edita_borrador and not confirma,
        "puede_actualizar_documental": actualiza_doc,
        "vista_previa": vista_previa_datos,
        "error_previa": error_previa,
        "max_entregables": settings.FICHA_MAX_ENTREGABLES,
    }
    if not ficha.confirmada and edita_borrador:
        form = form_borrador or FichaLevantamientoForm(usuario, instance=ficha)
        contexto.update(_contexto_editor(usuario, form))
    if ficha.confirmada and actualiza_doc:
        contexto["form_documental"] = form_documental or EstadoDocumentalForm(ficha)
    return contexto


@login_required
def lista(request):
    """Listado de fichas visibles con filtros por cliente, contrato y estado (de la ficha o documental)."""
    resultado = filtros.aplicar(_base(request.user), request.GET)
    fichas = list(
        resultado.queryset.annotate(n_entregables=Count("items__entregables_generados", distinct=True))
    )
    opciones = filtros.opciones(request.user)
    contexto = {
        "entidad": "fichas",
        "fichas": fichas,
        "total": len(fichas),
        "opciones": opciones,
        "filtros_activos": resultado.activos,
        "n_filtros": len(resultado.activos),
        "chips": filtros.chips(request.GET, resultado.activos, opciones),
        "puede_crear": contratos_para_ficha(request.user).exists(),
    }
    if pide_parcial(request):
        return con_vary(render(request, "levantamiento/_lista.html", {**contexto, "es_htmx": True}))
    return con_vary(render(request, "levantamiento/lista.html", contexto))


@login_required
def nueva(request):
    """Alta de una ficha de levantamiento en borrador."""
    contratos = contratos_para_ficha(request.user)
    cid = entero(request.GET.get("contrato"))
    contrato_inicial = contratos.filter(pk=cid).first() if cid is not None else None

    if request.method == "POST":
        form = FichaLevantamientoForm(request.user, request.POST, request.FILES)
        if form.is_valid():
            ficha = form.guardar(request.user)
            if request.POST.get("accion") == "vista_previa":
                try:
                    previa = servicios.calcular_vista_previa(ficha)
                except ValidationError as exc:
                    messages.error(request, " ".join(exc.messages))
                else:
                    messages.success(request, "Borrador guardado. Revise la vista previa antes de confirmar.")
                    return render(
                        request,
                        "levantamiento/detalle.html",
                        _contexto_detalle(request.user, ficha, vista_previa_datos=previa),
                    )
            messages.success(request, "Se guardó el borrador de la ficha de levantamiento.")
            return redirect("ficha_detalle", pk=ficha.pk)
    else:
        form = FichaLevantamientoForm(request.user, contrato_inicial=contrato_inicial)

    return render(
        request,
        "levantamiento/form.html",
        {"entidad": "fichas", **_contexto_editor(request.user, form)},
    )


@login_required
def detalle(request, pk):
    """Detalle de la ficha: edición del borrador (si no está confirmada) o estado inicial congelado y actual (HU-06)."""
    ficha = get_object_or_404(_base(request.user), pk=pk)

    if request.method == "POST":
        if ficha.confirmada:
            if not puede_actualizar_documental(request.user, ficha):
                raise PermissionDenied("No tiene permiso para actualizar el estado documental de esta ficha.")
            form_doc = EstadoDocumentalForm(ficha, request.POST)
            if form_doc.is_valid():
                d = form_doc.cleaned_data
                servicios.actualizar_estado_documental(
                    ficha,
                    request.user,
                    documentos_disponibles=d.get("documentos_disponibles", ""),
                    documentos_faltantes=d.get("documentos_faltantes", ""),
                    formato_esperado=d.get("formato_esperado", ""),
                    fecha_limite=d.get("fecha_limite"),
                    estado_documental=d["estado_documental"],
                )
                messages.success(request, "Se actualizó el estado documental actual. El estado inicial permanece intacto.")
                return redirect("ficha_detalle", pk=ficha.pk)
            return render(
                request,
                "levantamiento/detalle.html",
                _contexto_detalle(request.user, ficha, form_documental=form_doc),
            )

        if not puede_editar_borrador(request.user, ficha):
            raise PermissionDenied("No tiene permiso para editar esta ficha.")
        form = FichaLevantamientoForm(request.user, request.POST, request.FILES, instance=ficha)
        if form.is_valid():
            ficha = form.guardar(request.user)
            accion = request.POST.get("accion")
            if accion == "pedir_confirmacion":
                servicios.pedir_confirmacion(ficha, request.user)
                messages.success(
                    request,
                    f"Se guardó el borrador y se avisó a {ficha.contrato.senior_responsable.nombre} para su confirmación.",
                )
                return redirect("ficha_detalle", pk=ficha.pk)
            if accion == "vista_previa":
                try:
                    previa = servicios.calcular_vista_previa(ficha)
                except ValidationError as exc:
                    messages.error(request, " ".join(exc.messages))
                else:
                    return render(
                        request,
                        "levantamiento/detalle.html",
                        _contexto_detalle(request.user, ficha, vista_previa_datos=previa),
                    )
            messages.success(request, "Se guardaron los cambios del borrador de la ficha.")
            return redirect("ficha_detalle", pk=ficha.pk)
        return render(
            request,
            "levantamiento/detalle.html",
            _contexto_detalle(request.user, ficha, form_borrador=form),
        )

    return render(request, "levantamiento/detalle.html", _contexto_detalle(request.user, ficha))


@login_required
@require_POST
def vista_previa(request, pk):
    """Genera la vista previa de entregables antes de confirmar la ficha (§7.5 punto 3)."""
    ficha = get_object_or_404(_base(request.user), pk=pk)
    if not puede_editar_borrador(request.user, ficha) and not puede_confirmar(request.user, ficha):
        raise PermissionDenied("No tiene permiso para generar la vista previa de esta ficha.")
    if ficha.confirmada:
        messages.error(request, "Esta ficha ya fue confirmada.")
        return redirect("ficha_detalle", pk=ficha.pk)

    excluidos = request.POST.getlist("excluir")
    incluidos = request.POST.getlist("incluir") if "incluir" in request.POST else None
    try:
        previa = servicios.calcular_vista_previa(ficha, excluidos=excluidos, incluidos=incluidos)
    except ValidationError as exc:
        texto = " ".join(exc.messages)
        messages.error(request, f"No se puede generar la vista previa: {texto}")
        return render(
            request,
            "levantamiento/detalle.html",
            _contexto_detalle(request.user, ficha, error_previa=texto),
        )

    if previa["excede_maximo"]:
        messages.error(
            request,
            f"La ficha generaría {previa['total']} entregables y el máximo permitido por confirmación es {previa['maximo']}.",
        )
    return render(
        request,
        "levantamiento/detalle.html",
        _contexto_detalle(request.user, ficha, vista_previa_datos=previa),
    )


@login_required
@require_POST
def confirmar(request, pk):
    """Confirma la ficha y genera los entregables (solo senior del contrato, gerente o admin), o pide confirmación."""
    ficha = get_object_or_404(_base(request.user), pk=pk)

    if request.POST.get("accion") == "pedir_confirmacion":
        try:
            servicios.pedir_confirmacion(ficha, request.user)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(
                request,
                f"Se avisó a {ficha.contrato.senior_responsable.nombre} para que revise y confirme la ficha.",
            )
        return redirect("ficha_detalle", pk=ficha.pk)

    if not puede_confirmar(request.user, ficha):
        raise PermissionDenied("Solo el senior responsable del contrato, el gerente y el admin pueden confirmar la ficha.")

    excluidos = request.POST.getlist("excluir")
    incluidos = request.POST.getlist("incluir") if "incluir" in request.POST else None
    try:
        creados, omitidas = servicios.confirmar(ficha, request.user, excluidos=excluidos, incluidos=incluidos)
    except ValidationError as exc:
        texto = " ".join(exc.messages)
        messages.error(request, texto)
        return render(
            request,
            "levantamiento/detalle.html",
            _contexto_detalle(request.user, ficha, error_previa=texto),
        )

    n = len(creados)
    aviso = f"Ficha confirmada: se generaron {n} entregable{'s' if n != 1 else ''}."
    if omitidas:
        aviso += f" Se omitieron {omitidas} fecha{'s' if omitidas != 1 else ''} pasada{'s' if omitidas != 1 else ''}."
    messages.success(request, aviso)
    return redirect("ficha_detalle", pk=ficha.pk)


@login_required
def descargar_archivo(request, pk):
    """Descarga controlada del archivo del TDR: exige que la ficha sea visible para el usuario (404 si no)."""
    ficha = get_object_or_404(_base(request.user), pk=pk)
    try:
        archivo = ficha.archivo_tdr.open("rb")
    except (FileNotFoundError, ValueError):
        raise Http404("El archivo del TDR no se encuentra en el servidor.")
    respuesta = FileResponse(archivo, as_attachment=True, filename=ficha.nombre_archivo_tdr or "tdr.pdf")
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta
