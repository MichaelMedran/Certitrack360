import json
from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.clientes.models import PlantillaTDR
from apps.cuentas.permisos import solo_senior_o_superior

from . import adjuntos, filtros, servicios, subestado
from . import filtros_observaciones
from . import observaciones as obs_servicio
from .forms import AdjuntoForm, EntregableForm, ObservacionForm, contratos_para
from .htmx import con_vary, es_htmx, pide_parcial
from .models import Adjunto, Entregable, Observacion, TipoError
from .tipos import TipoAdjunto
from .visibilidad import entregables_visibles, es_senior_del_entregable

E = Entregable.Estado


def _base(usuario):
    return entregables_visibles(usuario).select_related(
        "contrato__cliente", "contrato__linea_servicio", "junior_asignado", "senior_revisor"
    )


def _enriquecer(entregables):
    """Agrega a cada entregable sus adjuntos y observaciones abiertas para las tarjetas (dos consultas en total)."""
    ids = [e.pk for e in entregables]
    adjuntos_por = dict(
        Adjunto.objects.filter(entregable_id__in=ids).values("entregable_id").annotate(n=Count("id"))
        .values_list("entregable_id", "n")
    )
    abiertas = defaultdict(list)
    for entregable_id, tipo in Observacion.objects.filter(entregable_id__in=ids, resuelta=False).values_list(
        "entregable_id", "tipo_error"
    ):
        abiertas[entregable_id].append(tipo)
    etiquetas = dict(TipoError.choices)
    for e in entregables:
        e.n_adjuntos = adjuntos_por.get(e.pk, 0)
        e.n_obs_abiertas = len(abiertas[e.pk])
        e.tipos_obs_abiertas = [etiquetas[t] for t in TipoError.values if t in abiertas[e.pk]]
        # «Con correcciones pendientes» (RF-26): En proceso con observaciones abiertas, sin consultas adicionales.
        e.con_correcciones = subestado.aplica(e, e.n_obs_abiertas > 0)
    return entregables


def _contexto_filtros(request, resultado):
    """Lo común del panel de filtros del tablero y de la lista."""
    opciones = filtros.opciones(request.user)
    return {
        "opciones": opciones, "filtros_activos": resultado.activos, "n_filtros": len(resultado.activos),
        "orden": resultado.orden, "chips": filtros.chips(request.GET, resultado.activos, opciones),
    }


def _respuesta(request, completa, parcial, contexto, status=200):
    """La página completa, o solo el fragmento de resultados cuando lo pide HTMX."""
    if pide_parcial(request):
        return con_vary(render(request, parcial, {**contexto, "es_htmx": True}, status=status))
    return con_vary(render(request, completa, contexto, status=status))


# ------------------------------------------------------------------ lista y tablero

@login_required
def lista(request):
    # Los filtros (cliente, contrato, responsable, estado, urgencia, tipo_observacion) y el orden viajan en la URL
    # y se aplican sobre el queryset ya restringido por rol: solo pueden reducirlo.
    resultado = filtros.aplicar(_base(request.user), request.GET)
    contexto = {"entregables": _enriquecer(list(resultado.queryset)), **_contexto_filtros(request, resultado)}
    return _respuesta(request, "entregables/lista.html", "entregables/_lista.html", contexto)


def _contexto_tablero(request):
    resultado = filtros.aplicar(_base(request.user), request.GET)
    tarjetas = _enriquecer(list(resultado.queryset))  # una sola consulta; ya viene filtrada y ordenada
    columnas = [
        {"valor": valor, "etiqueta": etiqueta, "tarjetas": [e for e in tarjetas if e.estado == valor]}
        for valor, etiqueta in E.choices
    ]
    return {"columnas": columnas, "total_tarjetas": len(tarjetas), **_contexto_filtros(request, resultado)}


@login_required
def tablero(request):
    return _respuesta(request, "entregables/tablero.html", "entregables/_tablero.html", _contexto_tablero(request))


# ------------------------------------------------------------------ cambio de estado

@login_required
@require_POST
def cambiar_estado(request, pk):
    """Cambia de estado un entregable (validado en el servidor).

    Desde el tablero llega por HTMX y se responde con el tablero ya actualizado: 200 si se movió, 422 si falta algo
    (la tarjeta vuelve a su columna y se explica el motivo) y 403 si no tiene permiso. Desde el detalle es un formulario
    clásico y se responde con un mensaje y una redirección.
    """
    e = get_object_or_404(_base(request.user), pk=pk)
    codigo, mensaje, pide_observacion = 200, None, False
    try:
        servicios.mover(
            e, request.POST.get("estado", ""), request.user,
            tipo_error=request.POST.get("tipo_error"), descripcion=request.POST.get("descripcion", ""),
        )
    except ValidationError as exc:
        codigo, mensaje = 422, " ".join(exc.messages)
        pide_observacion = getattr(exc, "code", None) == "observacion_requerida"
    except PermissionDenied as exc:
        codigo, mensaje = 403, str(exc) or "No tiene permiso para esa acción."

    if not es_htmx(request):
        if mensaje:
            messages.error(request, mensaje)
        else:
            messages.success(request, f"El entregable pasó a «{e.get_estado_display()}».")
        return redirect("entregable_detalle", pk=e.pk)

    # Si solo falta la observación y todavía no se envió ninguna, no hay nada que reprochar: se abre el diálogo.
    pidiendo = pide_observacion and not request.POST.get("tipo_error") and not request.POST.get("descripcion")
    contexto = {**_contexto_tablero(request), "es_htmx": True, "error": None if pidiendo else mensaje}
    if codigo == 200:
        contexto["exito"] = f"«{e.titulo}» pasó a «{e.get_estado_display()}»."
    respuesta = render(request, "entregables/_tablero.html", contexto, status=codigo)
    if pide_observacion:  # el tablero abre el diálogo de devolución (JSON en ASCII: viaja en una cabecera)
        respuesta["HX-Trigger"] = json.dumps({"pedirObservacion": {"id": e.pk, "titulo": e.titulo}})
    return con_vary(respuesta)


# ------------------------------------------------------------------ crear

@solo_senior_o_superior
def crear(request):
    usuario = request.user
    plantillas = PlantillaTDR.objects.select_related("cliente")
    plantilla = None
    # entero() y no str.isdigit(): «²» o «١» son dígitos para Python pero no un id, y la consulta fallaría con un error 500.
    pid = filtros.entero(request.POST.get("plantilla") or request.GET.get("plantilla"))
    if pid is not None:
        plantilla = plantillas.filter(pk=pid).first()

    form = None
    if plantilla:
        if request.method == "POST":
            form = EntregableForm(usuario, plantilla, request.POST)
            if form.is_valid():
                with transaction.atomic():  # el entregable (con su código), su historial y el aviso, o nada
                    entregable = form.guardar(usuario)
                    servicios.registrar_creacion(entregable, usuario)
                messages.success(request, f"El entregable {entregable.codigo} se creó y se asignó al junior.")
                return redirect("entregable_detalle", pk=entregable.pk)
        else:
            form = EntregableForm(usuario, plantilla)
    elif request.method == "POST":
        messages.error(request, "Primero elija una plantilla de TDR.")
    return render(request, "entregables/crear.html", {
        "plantillas": plantillas, "plantilla": plantilla, "form": form,
        "hay_contratos": contratos_para(usuario).exists(),
        # Ejemplo del formato del código que se asignará al guardar (p. ej. CT-2026-00031).
        "ejemplo_codigo": f"{settings.CODIGO_PREFIJO}-{timezone.localdate().year}-00031",
    })


# ------------------------------------------------------------------ detalle

@login_required
def detalle(request, pk):
    entregable = get_object_or_404(_base(request.user), pk=pk)  # 404 si no es visible
    return render(request, "entregables/detalle.html", _contexto_detalle(request.user, entregable))


def _contexto_detalle(usuario, e):
    es_senior = es_senior_del_entregable(usuario, e)
    siguientes = [
        (dest, E(dest).label)
        for (orig, dest), quien in servicios.TRANSICIONES.items()
        if orig == e.estado and (es_senior or (quien == "junior" and usuario.pk == e.junior_asignado_id))
    ]

    # Adjuntos: la versión más reciente de cada tipo y, plegadas, las anteriores (vienen de la más nueva a la más antigua).
    por_tipo = defaultdict(list)
    for a in e.adjuntos.select_related("subido_por"):
        por_tipo[a.tipo].append(a)
    posicion = {tipo: i for i, tipo in enumerate(TipoAdjunto.values)}
    grupos = [
        {"tipo": tipo, "etiqueta": adjuntos.etiqueta_tipo(tipo), "ultima": versiones[0], "anteriores": versiones[1:]}
        for tipo, versiones in sorted(por_tipo.items(), key=lambda par: posicion.get(par[0], 99))
    ]
    requeridos = [
        {"tipo": tipo, "etiqueta": adjuntos.etiqueta_tipo(tipo), "cumplido": tipo in por_tipo}
        for tipo in dict.fromkeys(t for t in e.plantilla.adjuntos_requeridos if t)
    ]
    puede_subir = adjuntos.puede_subir(usuario, e)

    # Observaciones con sus estados (RF-25): cada una sabe si el usuario puede registrar su corrección o revisarla.
    observaciones = list(e.observaciones.select_related(
        "autor", "responsable", "corregida_por", "revisada_por", "evidencia"
    ))
    for o in observaciones:
        o.puede_corregir = o.estado == Observacion.Estado.PENDIENTE and obs_servicio.puede_corregir(usuario, o, e)
        o.puede_revisar = o.estado == Observacion.Estado.EN_CORRECCION and es_senior
        o.puede_resolver = o.estado == Observacion.Estado.PENDIENTE and es_senior
    abiertas = [o for o in observaciones if o.abierta]

    # Qué falta para pasar a Revisión senior (datos, adjuntos y observaciones pendientes) o a Aprobado, antes de intentarlo.
    falta_para_verificar = None
    if e.estado == E.EN_PROCESO:
        motivos = [servicios.requisitos_para_verificacion(e),
                   servicios.observaciones_que_impiden(e, E.VERIFICACION_SENIOR)]
        falta_para_verificar = " ".join(m for m in motivos if m) or None
    falta_para_aprobar = (
        servicios.observaciones_que_impiden(e, E.LISTO_PARA_ENTREGA) if e.estado == E.VERIFICACION_SENIOR else None
    )

    return {
        "e": e, "es_senior": es_senior, "siguientes": siguientes,
        "admite_observaciones": obs_servicio.admite_observaciones(e),
        "observaciones": observaciones,
        "con_correcciones": subestado.aplica(e, bool(abiertas)), "etiqueta_subestado": subestado.ETIQUETA,
        "responsables_obs": servicios.responsables_posibles(e) if es_senior else [],
        "evidencias": obs_servicio.evidencias_posibles(e) if any(o.puede_corregir for o in observaciones) else [],
        "historial": e.historial.select_related("usuario"),
        # Dos formularios iguales en la misma página: identificadores distintos para que cada etiqueta apunte al suyo.
        "form_obs": ObservacionForm(auto_id="ob_%s"), "form_devolver": ObservacionForm(auto_id="dv_%s"),
        "grupos_adjuntos": grupos, "requeridos": requeridos,
        "puede_subir": puede_subir, "puede_eliminar": adjuntos.puede_eliminar(usuario),
        "junior_sin_subida": usuario.pk == e.junior_asignado_id and not puede_subir,
        "estados_de_subida": " o ".join(f"«{E(estado).label}»" for estado in adjuntos.ESTADOS_INICIALES),
        "form_adjunto": AdjuntoForm(),
        "extensiones": ", ".join(adjuntos.extensiones_permitidas()), "tamano_max": f"{settings.MEDIA_MAX_UPLOAD_MB:g}",
        "falta_para_verificar": falta_para_verificar, "falta_para_aprobar": falta_para_aprobar,
    }


# ------------------------------------------------------------------ adjuntos

@login_required
@require_POST
def adjunto_subir(request, pk):
    e = get_object_or_404(_base(request.user), pk=pk)
    if not adjuntos.puede_subir(request.user, e):
        raise PermissionDenied
    form = AdjuntoForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, " ".join(m for errores in form.errors.values() for m in errores))
    else:
        try:
            a = adjuntos.subir(
                e, request.user, form.cleaned_data["archivo"], form.cleaned_data["tipo"], form.cleaned_data["comentario"]
            )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, f"Se subió «{a.nombre_original}» como {adjuntos.etiqueta_tipo(a.tipo)} v{a.version}.")
    return redirect("entregable_detalle", pk=e.pk)


def _adjunto_visible(usuario, adjunto_id):
    """El adjunto solo existe para quien puede ver su entregable (si no, 404)."""
    return get_object_or_404(Adjunto.objects.filter(entregable__in=entregables_visibles(usuario)), pk=adjunto_id)


@login_required
def adjunto_descargar(request, adjunto_id):
    """Única vía de descarga: exige los mismos permisos de visibilidad que el entregable."""
    a = _adjunto_visible(request.user, adjunto_id)
    try:
        archivo = a.archivo.open("rb")
    except (FileNotFoundError, ValueError):
        raise Http404("El archivo no se encuentra en el servidor.")
    respuesta = FileResponse(archivo, as_attachment=True, filename=a.nombre_original)
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta


@login_required
@require_POST
def adjunto_eliminar(request, adjunto_id):
    a = _adjunto_visible(request.user, adjunto_id)
    entregable_id, nombre = a.entregable_id, a.nombre_original
    adjuntos.eliminar(a, request.user)  # PermissionDenied (403) si no es gerente o admin
    messages.success(request, f"Se eliminó «{nombre}».")
    return redirect("entregable_detalle", pk=entregable_id)


# ------------------------------------------------------------------ observaciones

def _volver_al_detalle(request, e):
    """Después de una acción sobre observaciones se vuelve a la sección Observaciones del detalle, con el mensaje.

    Desde HTMX se responde con HX-Redirect (htmx carga el detalle completo): la acción puede cambiar el estado, el
    subestado y lo que falta para avanzar, que están en otras partes de la página.
    """
    destino = reverse("entregable_detalle", args=[e.pk]) + "#observaciones"
    if es_htmx(request):
        respuesta = HttpResponse("")
        respuesta["HX-Redirect"] = destino
        return respuesta
    return redirect(destino)


def _observacion_visible(usuario, obs_id):
    """La observación solo existe para quien puede ver su entregable (si no, 404). Devuelve (observación, entregable)."""
    obs = get_object_or_404(obs_servicio.visibles(usuario), pk=obs_id)
    e = _base(usuario).get(pk=obs.entregable_id)
    obs.entregable = e  # mismo objeto, ya con su contrato y responsables
    return obs, e


def _filas_de_observaciones(request, e):
    """Las filas del formulario «Registrar observaciones»: parámetros repetidos tipo_error / descripcion / responsable.

    Una fila sin tipo ni descripción se ignora (filas vacías que agregó el botón «+ Otra observación»). Un responsable
    que no es una de las personas permitidas se rechaza en el servicio; uno que no es un id válido, aquí.
    """
    tipos, descripciones = request.POST.getlist("tipo_error"), request.POST.getlist("descripcion")
    responsables = request.POST.getlist("responsable")
    permitidos = {u.pk: u for u in servicios.responsables_posibles(e)}
    filas = []
    for i in range(max(len(tipos), len(descripciones))):
        tipo = tipos[i] if i < len(tipos) else ""
        descripcion = descripciones[i] if i < len(descripciones) else ""
        valor = responsables[i] if i < len(responsables) else ""
        if not tipo and not descripcion.strip():
            continue
        responsable = None
        if valor:
            rid = filtros.entero(valor)
            responsable = permitidos.get(rid) if rid is not None else None
            if responsable is None:
                raise ValidationError("El responsable debe ser el junior asignado o un senior del entregable.")
        filas.append({"tipo_error": tipo, "descripcion": descripcion, "responsable": responsable})
    return filas


@login_required
@require_POST
def registrar_observacion(request, pk):
    """Registra una o varias observaciones (RF-26). Si el entregable está en Revisión senior, vuelve a En proceso."""
    e = get_object_or_404(_base(request.user), pk=pk)
    if not obs_servicio.puede_registrar(request.user, e):
        raise PermissionDenied
    try:
        filas = _filas_de_observaciones(request, e)
        if not filas:
            raise ValidationError("Complete el tipo de error y la descripción de la observación.")
        creadas, devuelto = obs_servicio.registrar(e, request.user, filas)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        n = len(creadas)
        texto = "Observación registrada." if n == 1 else f"Se registraron {n} observaciones."
        if devuelto:
            texto += (f" El entregable volvió a «{E.EN_PROCESO.label}» con «{subestado.ETIQUETA}» y se avisó al junior.")
        else:
            texto += " Se avisó al junior."
        messages.success(request, texto)
    return _volver_al_detalle(request, e)


@login_required
@require_POST
def corregir_observacion(request, obs_id):
    """Registra la acción correctiva (PENDIENTE → EN_CORRECCION) y avisa al senior revisor."""
    obs, e = _observacion_visible(request.user, obs_id)
    if not obs_servicio.puede_corregir(request.user, obs, e):
        raise PermissionDenied
    try:
        obs_servicio.corregir(obs, request.user, request.POST.get("accion_correctiva", ""),
                              request.POST.get("evidencia") or None)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, f"Se registró la corrección: la observación quedó «{obs.get_estado_display()}» "
                                  "y se avisó al senior revisor.")
    return _volver_al_detalle(request, e)


@login_required
@require_POST
def revisar_observacion(request, obs_id):
    """Confirma (RESUELTA) o rechaza (vuelve a PENDIENTE y avisa al responsable) la corrección registrada."""
    obs, e = _observacion_visible(request.user, obs_id)
    if not obs_servicio.puede_revisar(request.user, e):
        raise PermissionDenied
    decision = request.POST.get("decision")
    try:
        if decision == "confirmar":
            obs_servicio.confirmar(obs, request.user)
            mensaje = "Corrección confirmada: la observación quedó «Resuelta»."
        elif decision == "rechazar":
            _, devuelto = obs_servicio.rechazar(obs, request.user, request.POST.get("motivo", ""))
            mensaje = "Corrección rechazada: la observación volvió a «Pendiente» y se avisó al responsable."
            if devuelto:
                mensaje += f" El entregable volvió a «{E.EN_PROCESO.label}» con «{subestado.ETIQUETA}»."
        else:
            raise ValidationError("Elija si confirma o rechaza la corrección.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, mensaje)
    return _volver_al_detalle(request, e)


@login_required
@require_POST
def resolver_observacion(request, obs_id):
    """Ruta del Sprint 1: el senior resuelve directamente con la solución (la acción correctiva)."""
    obs, e = _observacion_visible(request.user, obs_id)
    if not obs_servicio.puede_revisar(request.user, e):
        raise PermissionDenied
    try:
        obs_servicio.resolver(obs, request.user, request.POST.get("solucion", ""))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Observación resuelta.")
    return _volver_al_detalle(request, e)


# ------------------------------------------------------------------ historial de observaciones (RF-27)

@login_required
def historial_observaciones(request):
    """Pestaña «Observaciones» de Entregables: historial filtrable sobre los entregables visibles."""
    resultado = filtros_observaciones.aplicar(obs_servicio.visibles(request.user), request.GET)
    paginador = Paginator(resultado.queryset, 50)
    pagina = paginador.get_page(request.GET.get("pagina"))
    resto = request.GET.copy()
    resto.pop("pagina", None)
    opciones = filtros_observaciones.opciones(request.user)
    contexto = {
        "pagina": pagina, "observaciones": pagina.object_list, "total": paginador.count,
        "opciones": opciones, "filtros_activos": resultado.activos, "n_filtros": len(resultado.activos),
        "chips": filtros_observaciones.chips(request.GET, resultado.activos, opciones),
        "consulta_sin_pagina": resto.urlencode(), "pestana": "observaciones",
    }
    return _respuesta(request, "entregables/observaciones.html", "entregables/_observaciones_lista.html", contexto)
