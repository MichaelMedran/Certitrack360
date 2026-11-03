"""Vistas del repositorio de plantillas y ejemplos anonimizados (SDD del Sprint 2, RF-34 y RF-35: HU-07 y HU-20)."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Prefetch
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.clientes.models import LineaServicio
from apps.entregables import archivos
from apps.entregables.filtros import entero

from . import servicios
from .models import DocumentoRepositorio, RegistroAccesoDocumento, VersionDocumento
from .visibilidad import (
    clientes_para_cargar_plantilla,
    clientes_visibles_repositorio,
    documentos_visibles,
    puede_cargar_plantilla,
    puede_dar_de_baja,
    puede_mostrar_boton_cargar_plantilla,
    puede_publicar_anonimizado,
    puede_subir_version_o_restaurar,
    puede_ver_registro_accesos,
)


def _pestana_activa(params):
    p = (params.get("pestana") or "").strip().lower()
    cat = (params.get("categoria") or "").strip().upper()
    if p in ("anonimizados", "ejemplos") or cat == DocumentoRepositorio.Categoria.EJEMPLO_ANONIMIZADO:
        return "anonimizados"
    if p == "procedimientos":
        return "procedimientos"
    return "plantillas"


@login_required
def repositorio(request):
    """Pantalla principal `/repositorio/` con pestañas Plantillas de clientes, Ejemplos anonimizados y Procedimientos."""
    pestana = _pestana_activa(request.GET)
    incluir_inactivos = request.user.es_gerente_o_admin and request.GET.get("inactivos") in ("1", "si", "on")

    base_qs = (
        documentos_visibles(request.user, incluir_inactivos=incluir_inactivos)
        .select_related("cliente", "linea_servicio", "creado_por")
        .prefetch_related(
            Prefetch("versiones", queryset=VersionDocumento.objects.select_related("subido_por").order_by("-numero"))
        )
    )

    q = (request.GET.get("q") or request.GET.get("buscar") or "").strip()[:100]
    if q:
        base_qs = base_qs.filter(titulo__icontains=q)

    tipo = (request.GET.get("tipo") or request.GET.get("tipo_documento") or "").strip().upper()
    if tipo in DocumentoRepositorio.TipoDocumento.values:
        base_qs = base_qs.filter(tipo_documento=tipo)
    else:
        tipo = ""

    linea_id = entero(request.GET.get("linea") or request.GET.get("linea_servicio"))
    if linea_id is not None:
        base_qs = base_qs.filter(linea_servicio_id=linea_id)

    cliente_param = (request.GET.get("cliente") or "").strip()
    cliente_id = None
    solo_genericas = False
    if cliente_param == "generica":
        solo_genericas = True
    else:
        cliente_id = entero(cliente_param)

    plantillas_qs = base_qs.filter(categoria=DocumentoRepositorio.Categoria.PLANTILLA_CLIENTE)
    if solo_genericas:
        plantillas_qs = plantillas_qs.filter(cliente__isnull=True)
    elif cliente_id is not None:
        plantillas_qs = plantillas_qs.filter(cliente_id=cliente_id)

    anonimizados_qs = base_qs.filter(categoria=DocumentoRepositorio.Categoria.EJEMPLO_ANONIMIZADO)
    if cliente_id is not None or solo_genericas:
        # Si se filtra explícitamente por un cliente en una consulta general, los anonimizados no tienen cliente.
        if (request.GET.get("categoria") or "").upper() == DocumentoRepositorio.Categoria.PLANTILLA_CLIENTE:
            anonimizados_qs = anonimizados_qs.none()

    documentos = list(anonimizados_qs if pestana == "anonimizados" else plantillas_qs)

    # Pestaña «Procedimientos» (se poblará en S2-H11 cuando exista el modelo Procedimiento en `apps.conocimiento`).
    procedimientos = []
    try:
        from apps.conocimiento.models import Procedimiento  # noqa: PLC0415

        proc_qs = Procedimiento.objects.filter(vigente=True).select_related("linea_servicio", "aprobado_por", "documento")
        if q:
            proc_qs = proc_qs.filter(titulo__icontains=q)
        if linea_id is not None:
            proc_qs = proc_qs.filter(linea_servicio_id=linea_id)
        procedimientos = list(proc_qs)
    except (ImportError, LookupError):
        procedimientos = []

    clientes_filtro = clientes_visibles_repositorio(request.user).order_by("nombre")
    lineas_filtro = LineaServicio.objects.filter(activa=True).order_by("nombre")

    return render(
        request,
        "repositorio/lista.html",
        {
            "pestana": pestana,
            "documentos": documentos,
            "plantillas_docs": list(plantillas_qs),
            "anonimizados_docs": list(anonimizados_qs),
            "procedimientos": procedimientos,
            "clientes": clientes_filtro,
            "tipos": DocumentoRepositorio.TipoDocumento.choices,
            "lineas": lineas_filtro,
            "filtro_q": q,
            "filtro_cliente": "generica" if solo_genericas else cliente_id,
            "filtro_tipo": tipo,
            "filtro_linea": linea_id,
            "puede_cargar_plantilla": puede_mostrar_boton_cargar_plantilla(request.user),
            "puede_publicar_anonimizado": puede_publicar_anonimizado(request.user),
        },
    )


@login_required
def nuevo(request):
    """Alta de plantilla de cliente o publicación de ejemplo anonimizado (`/repositorio/nuevo/`)."""
    categoria_req = (
        request.POST.get("categoria")
        or request.GET.get("categoria")
        or DocumentoRepositorio.Categoria.PLANTILLA_CLIENTE
    ).strip().upper()
    if categoria_req not in DocumentoRepositorio.Categoria.values:
        categoria_req = DocumentoRepositorio.Categoria.PLANTILLA_CLIENTE

    es_anon = categoria_req == DocumentoRepositorio.Categoria.EJEMPLO_ANONIMIZADO
    if es_anon:
        if not puede_publicar_anonimizado(request.user):
            raise PermissionDenied("Solo los seniors, el gerente y el admin pueden publicar ejemplos anonimizados.")
    else:
        if not puede_mostrar_boton_cargar_plantilla(request.user) and not request.user.es_senior:
            raise PermissionDenied("No tiene permiso para cargar plantillas en el repositorio.")
        if request.user.es_junior:
            raise PermissionDenied("Los juniors no pueden cargar plantillas en el repositorio.")

    errores = []
    valores = {
        "categoria": categoria_req,
        "titulo": (request.POST.get("titulo") or "").strip(),
        "cliente": (request.POST.get("cliente") or "").strip(),
        "tipo_documento": (request.POST.get("tipo_documento") or "").strip(),
        "linea_servicio": (request.POST.get("linea_servicio") or "").strip(),
        "comentario": (request.POST.get("comentario") or "").strip(),
        "marcados_nda": set(),
    }

    if request.method == "POST":
        for clave in servicios.CLAVES_NDA:
            if request.POST.get(clave) in ("on", "1", "true", "si", "sí") or clave in request.POST.getlist("verificacion"):
                valores["marcados_nda"].add(clave)
        try:
            if es_anon:
                doc, _ = servicios.publicar_anonimizado(
                    request.user,
                    titulo=request.POST.get("titulo", ""),
                    tipo_documento=request.POST.get("tipo_documento", ""),
                    archivo=request.FILES.get("archivo"),
                    confirmaciones=request.POST,
                    linea_servicio=request.POST.get("linea_servicio"),
                    comentario=request.POST.get("comentario", ""),
                )
                messages.success(request, f"Se publicó el ejemplo anonimizado «{doc.titulo}».")
                return redirect("repositorio_documento", pk=doc.pk)

            doc, _ = servicios.cargar_plantilla(
                request.user,
                titulo=request.POST.get("titulo", ""),
                tipo_documento=request.POST.get("tipo_documento", ""),
                archivo=request.FILES.get("archivo"),
                cliente=request.POST.get("cliente"),
                linea_servicio=request.POST.get("linea_servicio"),
                comentario=request.POST.get("comentario", ""),
            )
            messages.success(request, f"Se guardó la plantilla «{doc.titulo}».")
            return redirect("repositorio_documento", pk=doc.pk)
        except ValidationError as exc:
            errores = list(exc.messages)
            for m in errores:
                messages.error(request, m)

    items_nda = [
        {"clave": clave, "etiqueta": etiqueta, "marcado": clave in valores["marcados_nda"]}
        for clave, etiqueta in servicios.ITEMS_VERIFICACION_NDA
    ]
    return render(
        request,
        "repositorio/nuevo.html",
        {
            "es_anonimizado": es_anon,
            "categoria": categoria_req,
            "valores": valores,
            "errores": errores,
            "items_nda": items_nda,
            "clientes": clientes_para_cargar_plantilla(request.user).order_by("nombre"),
            "admite_generica": puede_cargar_plantilla(request.user, None),
            "tipos": DocumentoRepositorio.TipoDocumento.choices,
            "lineas": LineaServicio.objects.filter(activa=True).order_by("nombre"),
            "extensiones": ", ".join(archivos.extensiones_permitidas()),
            "tamano_max": f"{settings.MEDIA_MAX_UPLOAD_MB:g}",
        },
    )


@login_required
def documento_detalle(request, pk):
    """Detalle del documento (`/repositorio/<pk>/`): versiones, subida de nueva versión, restauración, baja y accesos."""
    documento = get_object_or_404(
        documentos_visibles(request.user, incluir_inactivos=True).select_related(
            "cliente", "linea_servicio", "creado_por"
        ),
        pk=pk,
    )
    puede_editar = puede_subir_version_o_restaurar(request.user, documento)
    puede_baja = puede_dar_de_baja(request.user)
    puede_accesos = puede_ver_registro_accesos(request.user)

    if request.method == "POST":
        accion = (request.POST.get("accion") or "").strip().lower()
        if not accion:
            if "version" in request.POST or "version_id" in request.POST:
                accion = "restaurar"
            else:
                accion = "nueva_version"

        try:
            if accion == "restaurar":
                if not puede_editar:
                    raise PermissionDenied("No tiene permiso para restaurar versiones de este documento.")
                vid = entero(request.POST.get("version") or request.POST.get("version_id"))
                version_ant = get_object_or_404(VersionDocumento, pk=vid, documento=documento)
                nueva = servicios.restaurar_version(version_ant, request.user)
                messages.success(
                    request,
                    f"Se restauró la v{version_ant.numero} como vigente (nueva v{nueva.numero}).",
                )
                return redirect("repositorio_documento", pk=documento.pk)

            if accion in ("baja", "desactivar"):
                servicios.cambiar_estado_activo(documento, request.user, activo=False)
                messages.success(request, f"Se dio de baja el documento «{documento.titulo}».")
                return redirect("repositorio")

            if accion in ("activar", "reactivar"):
                servicios.cambiar_estado_activo(documento, request.user, activo=True)
                messages.success(request, f"Se reactivó el documento «{documento.titulo}».")
                return redirect("repositorio_documento", pk=documento.pk)

            if accion == "nueva_version":
                nueva = servicios.subir_nueva_version(
                    documento,
                    request.user,
                    archivo=request.FILES.get("archivo"),
                    comentario=request.POST.get("comentario", ""),
                    confirmaciones=request.POST if documento.es_anonimizado and any(
                        k in request.POST for k in servicios.CLAVES_NDA
                    ) else None,
                    exigir_comentario=True,
                )
                messages.success(request, f"Se cargó la v{nueva.numero} como versión vigente.")
                return redirect("repositorio_documento", pk=documento.pk)

            raise ValidationError("Acción no reconocida.")
        except ValidationError as exc:
            for m in exc.messages:
                messages.error(request, m)

    versiones = list(documento.versiones.select_related("subido_por").order_by("-numero", "-id"))
    vigente = next((v for v in versiones if v.vigente), versiones[0] if versiones else None)
    accesos = (
        list(
            RegistroAccesoDocumento.objects.filter(version__documento=documento)
            .select_related("usuario", "version")
            .order_by("-fecha", "-id")[:100]
        )
        if puede_accesos
        else []
    )

    return render(
        request,
        "repositorio/documento.html",
        {
            "documento": documento,
            "vigente": vigente,
            "versiones": versiones,
            "puede_editar": puede_editar,
            "puede_dar_de_baja": puede_baja,
            "puede_ver_accesos": puede_accesos,
            "accesos": accesos,
            "extensiones": ", ".join(archivos.extensiones_permitidas()),
            "tamano_max": f"{settings.MEDIA_MAX_UPLOAD_MB:g}",
        },
    )


@login_required
def descargar_version(request, pk):
    """Descarga controlada (`/repositorio/versiones/<pk>/descargar/`): verifica permisos (404 si no) y registra descarga."""
    version = get_object_or_404(VersionDocumento.objects.select_related("documento"), pk=pk)
    servicios.registrar_descarga(version, request.user)
    try:
        archivo = version.archivo.open("rb")
    except (FileNotFoundError, ValueError):
        raise Http404("El archivo no se encuentra en el servidor.")
    respuesta = FileResponse(archivo, as_attachment=True, filename=version.nombre_original or "documento")
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta
