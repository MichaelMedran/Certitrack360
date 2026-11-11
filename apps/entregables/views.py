import json
from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.clientes.models import PlantillaTDR
from apps.cuentas.models import Usuario
from apps.cuentas.permisos import solo_senior_o_superior
from apps.etiquetas import servicios as etiquetas_srv
from apps.etiquetas.models import Etiqueta

from . import adjuntos, entregas, extensiones, filtros, personal, prioridad, servicios, subestado, tiempos
from . import filtros_entregas, filtros_observaciones, filtros_tiempos
from . import observaciones as obs_servicio
from .forms import ActaForm, AdjuntoForm, EntregaForm, EntregableForm, ObservacionForm, contratos_para
from .htmx import con_vary, es_htmx, pide_parcial
from .models import Adjunto, Entrega, Entregable, Observacion, RegistroTiempo, ResponsableApoyo, TipoError
from .tipos import TIPOS_GENERADOS, TipoAdjunto
from .visibilidad import entregables_visibles, es_elaborador_del_entregable, es_senior_del_entregable

E = Entregable.Estado


def _base(usuario):
    return entregables_visibles(usuario).select_related(
        "contrato__cliente", "contrato__linea_servicio", "junior_asignado", "senior_revisor"
    )


def _enriquecer(entregables, usuario=None):
    """Agrega a cada entregable sus adjuntos y observaciones abiertas para las tarjetas (dos consultas en total).

    Los módulos del Sprint 3 suman lo suyo (etiquetas, prioridad, alerta urgente...) con `extensiones.registrar_tarjeta`.
    """
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
    # «Entregado»: la tarjeta muestra la fecha de entrega y el estado del acta en texto (última entrega, una consulta).
    ultimas = {}
    for entrega in Entrega.objects.filter(
        entregable_id__in=[e.pk for e in entregables if e.estado == E.HECHO]
    ).order_by("entregable_id", "numero"):
        ultimas[entrega.entregable_id] = entrega  # la de número más alto queda al final
    for e in entregables:
        e.ultima_entrega = ultimas.get(e.pk)
        e.n_adjuntos = adjuntos_por.get(e.pk, 0)
        e.n_obs_abiertas = len(abiertas[e.pk])
        e.tipos_obs_abiertas = [etiquetas[t] for t in TipoError.values if t in abiertas[e.pk]]
        # «Con correcciones pendientes» (RF-26): En proceso con observaciones abiertas, sin consultas adicionales.
        e.con_correcciones = subestado.aplica(e, e.n_obs_abiertas > 0)
    return extensiones.enriquecer_tarjetas(entregables, usuario)


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
    contexto = {"entregables": _enriquecer(list(resultado.queryset), request.user), **_contexto_filtros(request, resultado)}
    return _respuesta(request, "entregables/lista.html", "entregables/_lista.html", contexto)


def _contexto_tablero(request):
    resultado = filtros.aplicar(_base(request.user), request.GET)
    tarjetas = _enriquecer(list(resultado.queryset), request.user)  # una sola consulta; ya viene filtrada y ordenada
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
    codigo, mensaje, pide_observacion, advertencia = 200, None, False, None
    if (request.POST.get("estado") == E.HECHO and e.estado == E.LISTO_PARA_ENTREGA
            and entregas.puede_registrar(request.user, e)):
        # Pasar a «Entregado» exige el cargo de recepción (RF-29): soltar la tarjeta o pulsar el botón no la mueve, abre el
        # formulario de entrega. (Quien no puede entregar sigue por mover(), que responde 403.)
        destino = reverse("entregable_entregar", args=[e.pk])
        if es_htmx(request):
            respuesta = HttpResponse("")
            respuesta["HX-Redirect"] = destino
            return con_vary(respuesta)
        return redirect(destino)
    try:
        servicios.mover(
            e, request.POST.get("estado", ""), request.user,
            tipo_error=request.POST.get("tipo_error"), descripcion=request.POST.get("descripcion", ""),
            confirmadas=request.POST.getlist("confirmar"),
        )
    except ValidationError as exc:
        codigo, mensaje = 422, " ".join(exc.messages)
        if getattr(exc, "code", None) == "advertencia":  # no está prohibido: falta que el usuario lo confirme (§5.1)
            advertencia = {"id": e.pk, "titulo": e.titulo, "estado": request.POST.get("estado", ""),
                           "clave": exc.params["clave"], "mensaje": exc.params["mensaje"],
                           "confirmadas": request.POST.getlist("confirmar")}
        pide_observacion = getattr(exc, "code", None) == "observacion_requerida"
    except PermissionDenied as exc:
        codigo, mensaje = 403, str(exc) or "No tiene permiso para esa acción."

    if not es_htmx(request):
        if advertencia:  # el detalle se muestra con el aviso y el botón «Continuar de todos modos»
            contexto = _contexto_detalle(request.user, e)
            contexto["advertencia"] = advertencia
            return render(request, "entregables/detalle.html", contexto, status=422)
        if mensaje:
            messages.error(request, mensaje)
        else:
            messages.success(request, f"El entregable pasó a «{e.get_estado_display()}».")
        return redirect("entregable_detalle", pk=e.pk)

    # Si solo falta la observación y todavía no se envió ninguna, no hay nada que reprochar: se abre el diálogo.
    pidiendo = pide_observacion and not request.POST.get("tipo_error") and not request.POST.get("descripcion")
    contexto = {**_contexto_tablero(request), "es_htmx": True, "error": None if (pidiendo or advertencia) else mensaje}
    if codigo == 200:
        contexto["exito"] = f"«{e.titulo}» pasó a «{e.get_estado_display()}»."
    respuesta = render(request, "entregables/_tablero.html", contexto, status=codigo)
    if pide_observacion:  # el tablero abre el diálogo de devolución (JSON en ASCII: viaja en una cabecera)
        respuesta["HX-Trigger"] = json.dumps({"pedirObservacion": {"id": e.pk, "titulo": e.titulo}})
    if advertencia:  # el tablero abre el diálogo de confirmación y reenvía con «confirmar»
        respuesta["HX-Trigger"] = json.dumps({"confirmarAdvertencia": advertencia})
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
        "puede_crear_etiquetas": etiquetas_srv.puede_crear(usuario), "colores_etiqueta": Etiqueta.Color.choices,
        # Ejemplo del formato del código que se asignará al guardar (p. ej. CT-2026-00031).
        "ejemplo_codigo": f"{settings.CODIGO_PREFIJO}-{timezone.localdate().year}-00031",
    })


# ------------------------------------------------------------------ detalle

@login_required
def detalle(request, pk):
    entregable = get_object_or_404(_base(request.user), pk=pk)  # 404 si no es visible
    return render(request, "entregables/detalle.html", _contexto_detalle(request.user, entregable))


def _contexto_detalle(usuario, e):
    prioridad.enriquecer([e])  # prioridad calculada al momento (RF-42)
    es_senior = es_senior_del_entregable(usuario, e)
    es_elaborador = es_elaborador_del_entregable(usuario, e)
    siguientes = [
        (dest, E(dest).label)
        for (orig, dest), quien in servicios.TRANSICIONES.items()
        if orig == e.estado and (orig, dest) != servicios.REAPERTURA  # la reapertura tiene su propio formulario (Entregas)
        and (es_senior or (quien == "junior" and es_elaborador))
    ]

    # Adjuntos: la versión vigente de cada tipo (la de número más alto) y, plegadas, las anteriores (de la más nueva a la
    # más antigua). Restaurar solo se ofrece en las anteriores de los tipos que se versionan (no el cargo ni el acta).
    puede_restaurar = adjuntos.puede_restaurar(usuario, e)
    por_tipo = defaultdict(list)
    for a in e.adjuntos.select_related("subido_por", "restaurado_desde"):
        por_tipo[a.tipo].append(a)
    posicion = {tipo: i for i, tipo in enumerate(TipoAdjunto.values)}
    grupos = [
        {"tipo": tipo, "etiqueta": adjuntos.etiqueta_tipo(tipo), "ultima": versiones[0], "anteriores": versiones[1:]}
        for tipo, versiones in sorted(por_tipo.items(), key=lambda par: posicion.get(par[0], 99))
    ]
    for g in grupos:
        g["ultima"].puede_restaurar = False
        for a in g["anteriores"]:
            a.puede_restaurar = puede_restaurar and a.tipo not in TIPOS_GENERADOS

    # Entregas y acta (RF-29): historial de entregas del entregable, con lo que el usuario puede hacer sobre ellas.
    lista_entregas = list(e.entregas.select_related("cargo", "version_enviada", "acta", "registrada_por").order_by("numero"))
    ultima_entrega = lista_entregas[-1] if lista_entregas else None
    for entrega in lista_entregas:
        entrega.dias_pendiente = entrega.dias_acta_pendiente()
    puede_entregar = es_senior and e.estado == E.LISTO_PARA_ENTREGA
    puede_acta = es_senior and e.estado == E.HECHO and ultima_entrega is not None
    puede_reabrir = es_senior and servicios.puede_reabrir(e)
    requeridos = [
        {"tipo": tipo, "etiqueta": adjuntos.etiqueta_tipo(tipo), "cumplido": tipo in por_tipo}
        for tipo in dict.fromkeys(t for t in e.plantilla.adjuntos_requeridos if t)
    ]
    puede_subir = adjuntos.puede_subir(usuario, e)

    # Responsables de apoyo activos (RF-31)
    apoyos_activos = list(
        e.responsables_apoyo.filter(activo=True).select_related("usuario", "asignado_por").order_by("asignado_en", "id")
    )
    puede_gestionar_resp = personal.puede_gestionar_responsables(usuario, e)
    colaboradores_apoyo = (
        list(
            Usuario.objects.filter(
                rol__in=(Usuario.Rol.JUNIOR, Usuario.Rol.SENIOR), is_active=True
            ).order_by("first_name", "last_name", "username")
        )
        if puede_gestionar_resp
        else []
    )
    juniors_disponibles = [u for u in colaboradores_apoyo if u.rol == Usuario.Rol.JUNIOR]
    seniors_disponibles = [u for u in colaboradores_apoyo if u.rol == Usuario.Rol.SENIOR]

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
        "secciones": extensiones.secciones(usuario, e),
        "apoyos_activos": apoyos_activos,
        "puede_gestionar_responsables": puede_gestionar_resp,
        "juniors_disponibles": juniors_disponibles,
        "seniors_disponibles": seniors_disponibles,
        "colaboradores_apoyo": colaboradores_apoyo,
        "funciones_apoyo": ResponsableApoyo.Funcion.choices,
        "resumen_tiempo": tiempos.resumen_tiempos(e, usuario=usuario),
        "puede_registrar_tiempo": tiempos.puede_registrar_tiempo(usuario, e),
        "etapas_tiempo": RegistroTiempo.Etapa.choices,
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
        "junior_sin_subida": es_elaborador and not es_senior and not puede_subir,
        "estados_de_subida": " o ".join(f"«{E(estado).label}»" for estado in adjuntos.ESTADOS_INICIALES),
        "form_adjunto": AdjuntoForm(), "puede_restaurar": puede_restaurar,
        "entregas": lista_entregas, "ultima_entrega": ultima_entrega, "puede_entregar": puede_entregar,
        "puede_acta": puede_acta, "puede_reabrir": puede_reabrir,
        "form_acta": ActaForm(auto_id="ac_%s") if puede_acta else None,
        "form_reabrir": ObservacionForm(auto_id="re_%s") if puede_reabrir else None,
        "extensiones": ", ".join(adjuntos.extensiones_permitidas()), "tamano_max": f"{settings.MEDIA_MAX_UPLOAD_MB:g}",
        "falta_para_verificar": falta_para_verificar, "falta_para_aprobar": falta_para_aprobar,
    }


# ------------------------------------------------------------------ responsables (RF-31)

def _volver_a_responsables(request, e):
    destino = personal.enlace_responsables(e)
    if es_htmx(request):
        respuesta = HttpResponse("")
        respuesta["HX-Redirect"] = destino
        return con_vary(respuesta)
    return redirect(destino)


@login_required
@require_POST
def gestionar_responsables(request, pk):
    """POST /entregables/<pk>/responsables/: reasignar junior/senior principal, sumar apoyo o quitar apoyo (RF-31)."""
    e = get_object_or_404(_base(request.user), pk=pk)  # 404 si no lo ve
    if not personal.puede_gestionar_responsables(request.user, e):
        raise PermissionDenied("Solo el senior del entregable, el gerente y el admin gestionan responsables.")

    accion = (request.POST.get("accion") or "").strip()
    confirmar = request.POST.get("confirmar") in ("1", "true", "si", "on")

    try:
        if accion in ("reasignar", "reasignar_junior", "reasignar_senior"):
            rol = request.POST.get("rol") or ("senior" if accion == "reasignar_senior" else "junior")
            usuario_id = (
                request.POST.get("usuario")
                or request.POST.get("nuevo_usuario")
                or request.POST.get("junior_asignado")
                or request.POST.get("senior_revisor")
            )
            motivo = request.POST.get("motivo", "")
            res = personal.reasignar_principal(e, rol, usuario_id, request.user, motivo=motivo, confirmar=confirmar)
            if not res.confirmado:
                ctx = _contexto_detalle(request.user, e)
                ctx["conflicto_responsables"] = {
                    "accion": "reasignar",
                    "rol": rol,
                    "usuario": usuario_id,
                    "motivo": motivo,
                    "conflictos": res.conflictos,
                }
                return con_vary(render(request, "entregables/detalle.html", ctx))
            messages.success(request, "Se reasignó el responsable del entregable.")
            return _volver_a_responsables(request, e)

        if accion in ("sumar_apoyo", "apoyo"):
            usuario_id = request.POST.get("usuario")
            funcion = request.POST.get("funcion") or ResponsableApoyo.Funcion.ELABORACION
            fecha_limite = request.POST.get("fecha_limite") or None
            res = personal.sumar_apoyo(
                e, usuario_id, funcion=funcion, autor=request.user, fecha_limite=fecha_limite, confirmar=confirmar
            )
            if not res.confirmado:
                ctx = _contexto_detalle(request.user, e)
                ctx["conflicto_responsables"] = {
                    "accion": "sumar_apoyo",
                    "usuario": usuario_id,
                    "funcion": funcion,
                    "fecha_limite": fecha_limite or "",
                    "conflictos": res.conflictos,
                }
                return con_vary(render(request, "entregables/detalle.html", ctx))
            ap = res.objeto
            messages.success(
                request, f"Se sumó a {ap.usuario.nombre} como apoyo ({ap.get_funcion_display().lower()})."
            )
            return _volver_a_responsables(request, e)

        if accion in ("quitar_apoyo", "quitar"):
            apoyo_id = filtros.entero(request.POST.get("apoyo_id") or request.POST.get("apoyo"))
            if apoyo_id is None:
                raise Http404("No existe ese responsable de apoyo.")
            apoyo = get_object_or_404(ResponsableApoyo.objects.select_related("usuario"), pk=apoyo_id, entregable=e)
            personal.quitar_apoyo(apoyo, request.user)
            messages.success(request, f"Se quitó a {apoyo.usuario.nombre} como apoyo.")
            return _volver_a_responsables(request, e)

        raise ValidationError("Elija una acción válida sobre los responsables del entregable.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return _volver_a_responsables(request, e)


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
    # PermissionDenied (403) si no es gerente o admin, o si la versión está bloqueada por una entrega (RF-28): ni siquiera
    # el gerente o el admin la eliminan, y la página 403 dice el motivo.
    adjuntos.eliminar(a, request.user)
    messages.success(request, f"Se eliminó «{nombre}».")
    return redirect("entregable_detalle", pk=entregable_id)


@login_required
@require_POST
def adjunto_restaurar(request, adjunto_id):
    """Restaura una versión anterior como vigente: crea una versión NUEVA (senior del entregable, gerente y admin)."""
    a = _adjunto_visible(request.user, adjunto_id)
    e = _base(request.user).get(pk=a.entregable_id)
    a.entregable = e
    if not adjuntos.puede_restaurar(request.user, e):
        raise PermissionDenied("Solo el senior del entregable, el gerente y el admin restauran versiones.")
    try:
        nueva = adjuntos.restaurar(a, request.user)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(
            request, f"Se restauró la v{a.version} de {adjuntos.etiqueta_tipo(a.tipo)}: ahora es la v{nueva.version}, la versión vigente."
        )
    return redirect(reverse("entregable_detalle", args=[e.pk]) + "#adjuntos")


# ------------------------------------------------------------------ entregas y actas (RF-29)

def _volver_a_entregas(e):
    return redirect(reverse("entregable_detalle", args=[e.pk]) + "#entregas")


@login_required
def entregar(request, pk):
    """«Marcar como entregado»: formulario de entrega (fecha, medio, cargo y versión enviada). Al guardar, en una
    transacción, crea el cargo y la entrega, bloquea la versión enviada y pasa el entregable a «Entregado»."""
    e = get_object_or_404(_base(request.user), pk=pk)  # 404 si no lo ve
    if not entregas.puede_registrar(request.user, e):
        raise PermissionDenied("Solo el senior del entregable, el gerente y el admin registran entregas.")
    if e.estado != E.LISTO_PARA_ENTREGA:
        messages.error(request, f"Solo se registra la entrega de un entregable «{E.LISTO_PARA_ENTREGA.label}»; "
                                f"este está «{e.get_estado_display()}».")
        return redirect("entregable_detalle", pk=e.pk)
    if request.method == "POST":
        form = EntregaForm(e, request.POST, request.FILES)
        if form.is_valid():
            d = form.cleaned_data
            try:
                entrega = entregas.registrar(
                    e, request.user, d["fecha_entrega"], d["medio"], d["cargo"], d["version_enviada"], d["comentario"]
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, f"Entrega n.º {entrega.numero} registrada: «{e.titulo}» pasó a «{e.get_estado_display()}». "
                                          "El acta de conformidad queda pendiente.")
                return _volver_a_entregas(e)
    else:
        form = EntregaForm(e)
    return render(request, "entregables/entregar.html", {
        "e": e, "form": form, "extensiones": ", ".join(adjuntos.extensiones_permitidas()),
        "tamano_max": f"{settings.MEDIA_MAX_UPLOAD_MB:g}", "numero": e.entregas.count() + 1,
        "acta_dias": settings.ACTA_DIAS_PENDIENTE,
        "sin_version_final": entregas.version_por_defecto(e) is None,
    })


@login_required
@require_POST
def entrega_acta(request, entrega_id):
    """Registra o actualiza el acta de conformidad de la entrega: Recibida u Observada, con su archivo."""
    entrega = get_object_or_404(entregas.visibles(request.user).select_related("entregable"), pk=entrega_id)
    e = _base(request.user).get(pk=entrega.entregable_id)
    entrega.entregable = e
    if not entregas.puede_registrar(request.user, e):
        raise PermissionDenied("Solo el senior del entregable, el gerente y el admin registran el acta.")
    form = ActaForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, " ".join(m for errores in form.errors.values() for m in errores))
        return _volver_a_entregas(e)
    try:
        entregas.registrar_acta(entrega, request.user, form.cleaned_data["estado"], form.cleaned_data["archivo"])
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        estado = Entrega.ActaEstado(form.cleaned_data["estado"]).label.lower()
        texto = f"Acta de la entrega n.º {entrega.numero} registrada como {estado}."
        if form.cleaned_data["estado"] == Entrega.ActaEstado.OBSERVADA:
            texto += " Puede reabrir el entregable para corrección."
        messages.success(request, texto)
    return _volver_a_entregas(e)


@login_required
def historial_entregas(request):
    """Pestaña «Entregas» de Entregables: historial filtrable sobre los entregables visibles (RF-29)."""
    resultado = filtros_entregas.aplicar(entregas.visibles(request.user), request.GET)
    paginador = Paginator(resultado.queryset, 50)
    pagina = paginador.get_page(request.GET.get("pagina"))
    resto = request.GET.copy()
    resto.pop("pagina", None)
    opciones = filtros_entregas.opciones(request.user)
    hoy = timezone.localdate()
    filas = list(pagina.object_list)
    for entrega in filas:
        entrega.dias_pendiente = entrega.dias_acta_pendiente(hoy)
    contexto = {
        "pagina": pagina, "entregas": filas, "total": paginador.count,
        "opciones": opciones, "filtros_activos": resultado.activos, "n_filtros": len(resultado.activos),
        "chips": filtros_entregas.chips(request.GET, resultado.activos, opciones),
        "consulta_sin_pagina": resto.urlencode(), "pestana": "entregas", "acta_dias": settings.ACTA_DIAS_PENDIENTE,
    }
    return _respuesta(request, "entregables/entregas.html", "entregables/_entregas_lista.html", contexto)


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



# ------------------------------------------------------------------ tiempo por etapa (RF-32)

def _volver_a_tiempo(request, e):
    destino = tiempos.enlace_tiempo(e)
    if es_htmx(request):
        respuesta = HttpResponse("")
        respuesta["HX-Redirect"] = destino
        return con_vary(respuesta)
    return redirect(destino)


@login_required
@require_POST
def gestionar_tiempo(request, pk):
    """POST /entregables/<pk>/tiempo/: iniciar, pausar, finalizar etapa o registrar ajuste manual (RF-32)."""
    e = get_object_or_404(_base(request.user), pk=pk)  # 404 si no lo ve
    if not tiempos.puede_registrar_tiempo(request.user, e):
        raise PermissionDenied("Solo los responsables del entregable pueden registrar tiempo.")

    accion = (request.POST.get("accion") or "").strip().lower()
    etapa = (request.POST.get("etapa") or "").strip()

    try:
        if accion == "iniciar":
            nuevo, pausado = tiempos.iniciar(e, request.user, etapa)
            msg = f"Se inició el registro de tiempo en «{nuevo.get_etapa_display()}»."
            if pausado is not None:
                msg += f" Se pausó el tramo abierto en {pausado.entregable.referencia}."
            messages.success(request, msg)
        elif accion == "pausar":
            reg = tiempos.pausar(e, request.user)
            messages.success(
                request, f"Se pausó el tramo de «{reg.get_etapa_display()}» ({reg.duracion_texto})."
            )
        elif accion in ("finalizar", "finalizar_etapa"):
            reg = tiempos.finalizar_etapa(e, request.user, etapa=etapa or None)
            messages.success(request, f"La etapa «{reg.get_etapa_display()}» quedó marcada como finalizada.")
        elif accion in ("manual", "ajuste_manual"):
            cierra = request.POST.get("cierra_etapa") in ("1", "true", "si", "on")
            reg = tiempos.registrar_manual(
                e,
                request.user,
                etapa=etapa,
                inicio=request.POST.get("inicio"),
                fin=request.POST.get("fin"),
                motivo=request.POST.get("motivo", ""),
                cierra_etapa=cierra,
            )
            messages.success(
                request, f"Se registró el ajuste manual en «{reg.get_etapa_display()}» ({reg.duracion_texto})."
            )
        else:
            raise ValidationError("Elija una acción válida sobre el tiempo por etapa.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return _volver_a_tiempo(request, e)


@login_required
def historial_tiempos(request):
    """Pestaña «Tiempos» de Entregables (/tiempos/): historial filtrable según visibilidad del rol (RF-32)."""
    resultado = filtros_tiempos.aplicar(tiempos.visibles(request.user), request.GET)
    paginador = Paginator(resultado.queryset, 50)
    pagina = paginador.get_page(request.GET.get("pagina"))
    resto = request.GET.copy()
    resto.pop("pagina", None)
    opciones = filtros_tiempos.opciones(request.user)
    contexto = {
        "pagina": pagina,
        "registros": pagina.object_list,
        "total": paginador.count,
        "total_segundos": resultado.total_segundos,
        "total_texto": resultado.total_texto,
        "opciones": opciones,
        "filtros_activos": resultado.activos,
        "n_filtros": len(resultado.activos),
        "chips": filtros_tiempos.chips(request.GET, resultado.activos, opciones),
        "consulta_sin_pagina": resto.urlencode(),
        "pestana": "tiempos",
    }
    return _respuesta(request, "entregables/tiempos.html", "entregables/_tiempos_lista.html", contexto)
