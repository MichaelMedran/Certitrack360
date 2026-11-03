"""Vistas del asistente y gestión de procedimientos aprobados (SDD RF-19; SDD Sprint 2 RF-37: HU-10)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.clientes.models import LineaServicio
from apps.cuentas.permisos import solo_gestion
from apps.entregables.filtros import entero
from apps.repositorio.models import DocumentoRepositorio

from . import servicios
from .models import ConsultaAsistente, Procedimiento


@login_required
def asistente(request):
    pregunta = request.GET.get("q", "").strip()
    contexto = {"pregunta": pregunta}
    if "consulta" in request.GET and not pregunta:
        cid = entero(request.GET.get("consulta"))
        if cid is None:
            raise Http404("No existe esa consulta.")
        consulta_obj = get_object_or_404(ConsultaAsistente, pk=cid, usuario=request.user)
        contexto.update(servicios.reconstruir_consulta(consulta_obj, request.user))
    elif pregunta:
        contexto.update(servicios.responder(pregunta, request.user))
        contexto["buscado"] = True
    contexto["historial_consultas"] = list(
        ConsultaAsistente.objects.filter(usuario=request.user).order_by("-creada_en", "-id")[:25]
    )
    return render(request, "conocimiento/asistente.html", contexto)


@login_required
@require_POST
def valorar(request, pk):
    """Guarda la valoración «¿Le sirvió esta respuesta? Sí / No» de una consulta propia (`POST /asistente/valorar/<pk>/`)."""
    consulta = get_object_or_404(ConsultaAsistente, pk=pk, usuario=request.user)
    valor = request.POST.get("util") if "util" in request.POST else request.POST.get("valor", "")
    try:
        servicios.valorar_consulta(consulta, request.user, valor)
        messages.success(request, "Gracias. Se guardó su valoración.")
    except ValidationError as exc:
        for m in exc.messages:
            messages.error(request, m)
    return redirect(f"{reverse('asistente')}?consulta={consulta.pk}")


def _procedimiento_o_404(valor):
    pk = entero(valor)
    if pk is None:
        raise Http404("No existe ese procedimiento.")
    return get_object_or_404(Procedimiento, pk=pk)


@solo_gestion
def procedimientos(request):
    """Carga, edición y aprobación de procedimientos del asistente (`/procedimientos/`, solo gerente y admin: §7.11, §8)."""
    editando = None
    errores = []
    valores = {
        "titulo": "",
        "contenido": "",
        "linea_servicio": "",
        "documento": "",
        "vigente": True,
    }

    if request.method == "POST":
        accion = (request.POST.get("accion") or "").strip().lower()
        proc_id = request.POST.get("procedimiento") or request.POST.get("id")
        if proc_id not in (None, ""):
            editando = _procedimiento_o_404(proc_id)

        if accion in ("cambiar_vigencia", "desactivar", "activar") and editando is not None:
            if accion == "desactivar":
                editando.vigente = False
            elif accion == "activar":
                editando.vigente = True
            else:
                editando.vigente = not editando.vigente
            editando.save(update_fields=["vigente"])
            estado_txt = "vigente" if editando.vigente else "no vigente"
            messages.success(request, f"El procedimiento «{editando.titulo}» quedó {estado_txt}.")
            return redirect("procedimientos")

        vigente_raw = request.POST.get("vigente")
        if vigente_raw is None:
            # En el alta sin casilla explícita nace vigente; en edición por formulario respeta la casilla si viene del form.
            vigente_val = True if editando is None or " desde_form" not in request.POST else False
            if "form_edicion" in request.POST:
                vigente_val = False
        else:
            vigente_val = str(vigente_raw).strip().lower() not in ("0", "false", "no", "off", "")

        linea_raw = request.POST.get("linea_servicio") or request.POST.get("linea") or ""
        doc_raw = request.POST.get("documento") or ""
        valores = {
            "titulo": (request.POST.get("titulo") or "").strip(),
            "contenido": (request.POST.get("contenido") or "").strip(),
            "linea_servicio": entero(linea_raw) or "",
            "documento": entero(doc_raw) or "",
            "vigente": vigente_val,
        }
        try:
            proc = servicios.guardar_procedimiento(
                request.user,
                titulo=request.POST.get("titulo", ""),
                contenido=request.POST.get("contenido", ""),
                linea_servicio=linea_raw,
                documento=doc_raw,
                vigente=vigente_val,
                procedimiento=editando,
            )
            verbo = "Se actualizaron los datos de" if editando else "Se aprobó y guardó"
            messages.success(request, f"{verbo} «{proc.titulo}».")
            return redirect("procedimientos")
        except ValidationError as exc:
            errores = list(exc.messages)
            for m in errores:
                messages.error(request, m)
    elif "editar" in request.GET:
        editando = _procedimiento_o_404(request.GET.get("editar"))
        valores = {
            "titulo": editando.titulo,
            "contenido": editando.contenido,
            "linea_servicio": editando.linea_servicio_id or "",
            "documento": editando.documento_id or "",
            "vigente": editando.vigente,
        }

    lista_proc = list(
        Procedimiento.objects.select_related("linea_servicio", "aprobado_por", "documento").order_by(
            "-vigente", "titulo", "-id"
        )
    )
    return render(
        request,
        "conocimiento/procedimientos.html",
        {
            "procedimientos": lista_proc,
            "editando": editando,
            "valores": valores,
            "errores": errores,
            "lineas": LineaServicio.objects.filter(activa=True).order_by("nombre"),
            "documentos": DocumentoRepositorio.objects.filter(activo=True).order_by("titulo"),
        },
    )
