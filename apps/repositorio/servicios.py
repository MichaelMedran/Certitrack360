"""Servicios del repositorio de plantillas y ejemplos anonimizados (SDD del Sprint 2, RF-34 y RF-35, §7.9)."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
from django.http import Http404
from django.utils import timezone

from apps.clientes.models import Cliente, LineaServicio
from apps.entregables.archivos import validar_archivo
from apps.entregables.filtros import entero

from .models import DocumentoRepositorio, RegistroAccesoDocumento, VersionDocumento
from .visibilidad import (
    documentos_visibles,
    puede_cargar_plantilla,
    puede_dar_de_baja,
    puede_publicar_anonimizado,
    puede_subir_version_o_restaurar,
)

ITEMS_VERIFICACION_NDA = (
    ("nombres", "Nombres de clientes y de personas de contacto"),
    ("montos", "Montos y valores económicos"),
    ("contratos", "Números de contrato, de TDR y de factura"),
    ("datos_personales", "Datos personales (documentos de identidad, direcciones, teléfonos, correos)"),
)
CLAVES_NDA = tuple(clave for clave, _ in ITEMS_VERIFICACION_NDA)


def _resolver_cliente(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, Cliente):
        return valor
    cid = entero(valor)
    if cid is None:
        raise ValidationError("El cliente seleccionado no es válido.")
    cliente = Cliente.objects.filter(pk=cid).first()
    if cliente is None:
        raise ValidationError("El cliente seleccionado no existe.")
    return cliente


def _resolver_linea(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, LineaServicio):
        return valor
    lid = entero(valor)
    if lid is None:
        raise ValidationError("La línea de servicio seleccionada no es válida.")
    linea = LineaServicio.objects.filter(pk=lid).first()
    if linea is None:
        raise ValidationError("La línea de servicio seleccionada no existe.")
    return linea


def validar_verificacion_nda(confirmaciones, usuario):
    """Verifica que los 4 ítems de anonimización (política NDA) estén confirmados (RF-35, `s2-repositorio.html`).

    Acepta un diccionario/`QueryDict` (con claves `nombres`, `montos`, `contratos`, `datos_personales` o lista
    `verificacion`) o un iterable de claves confirmadas.
    """
    marcados = set()
    if confirmaciones is not None:
        if hasattr(confirmaciones, "getlist"):
            for item in confirmaciones.getlist("verificacion"):
                if item in CLAVES_NDA:
                    marcados.add(item)
        if isinstance(confirmaciones, dict):
            for clave in CLAVES_NDA:
                val = confirmaciones.get(clave)
                if val in (True, "on", "1", "true", "si", "sí", 1):
                    marcados.add(clave)
            lista = confirmaciones.get("verificacion") or confirmaciones.get("items_confirmados")
            if isinstance(lista, (list, tuple, set)):
                for item in lista:
                    if item in CLAVES_NDA:
                        marcados.add(item)
        elif isinstance(confirmaciones, (list, tuple, set)):
            for item in confirmaciones:
                if item in CLAVES_NDA:
                    marcados.add(item)

    faltantes = [clave for clave in CLAVES_NDA if clave not in marcados]
    if faltantes:
        n = len(faltantes)
        detalle = "falta 1 confirmación" if n == 1 else f"faltan {n} confirmaciones"
        raise ValidationError(f"No se puede publicar: {detalle} de la lista.")

    return {
        "items_confirmados": list(CLAVES_NDA),
        "confirmado_por_id": usuario.pk,
        "confirmado_por": usuario.username,
        "confirmado_en": timezone.now().isoformat(),
    }


def _crear_version_y_acceso(documento, usuario, archivo, nombre_limpio, comentario="", verificacion=None, accion=None):
    """Desmarca la versión vigente anterior, crea la nueva como `vigente=True` y registra el acceso."""
    DocumentoRepositorio.objects.select_for_update().get(pk=documento.pk)
    ultima = VersionDocumento.objects.filter(documento=documento).aggregate(m=Max("numero"))["m"] or 0
    VersionDocumento.objects.filter(documento=documento, vigente=True).update(vigente=False)
    archivo.name = nombre_limpio
    version = VersionDocumento.objects.create(
        documento=documento,
        numero=ultima + 1,
        archivo=archivo,
        nombre_original=nombre_limpio,
        comentario=(comentario or "").strip()[:255],
        vigente=True,
        subido_por=usuario,
        verificacion_anonimizacion=verificacion or {},
    )
    RegistroAccesoDocumento.objects.create(
        version=version,
        usuario=usuario,
        accion=accion or RegistroAccesoDocumento.Accion.CARGA,
    )
    return version


@transaction.atomic
def cargar_plantilla(
    usuario,
    *,
    titulo,
    tipo_documento,
    archivo,
    cliente=None,
    linea_servicio=None,
    comentario="",
):
    """Carga una plantilla de cliente (o genérica) en el repositorio (RF-34, HU-07).

    Si ya existe una plantilla activa con el mismo título y el mismo cliente, crea una nueva versión vigente y deja la
    anterior como histórico (`s2-repositorio.html`, anotación 2).
    """
    cliente_obj = _resolver_cliente(cliente)
    if not puede_cargar_plantilla(usuario, cliente_obj):
        raise PermissionDenied("No tiene permiso para cargar plantillas para este cliente.")

    titulo_limpio = " ".join((titulo or "").split())
    if not titulo_limpio:
        raise ValidationError("Escriba el título de la plantilla.")
    if tipo_documento not in DocumentoRepositorio.TipoDocumento.values:
        raise ValidationError("Elija un tipo de documento válido.")
    if archivo is None:
        raise ValidationError("Seleccione el archivo de la plantilla.")

    linea_obj = _resolver_linea(linea_servicio)
    nombre_limpio = validar_archivo(archivo)

    existente = DocumentoRepositorio.objects.filter(
        categoria=DocumentoRepositorio.Categoria.PLANTILLA_CLIENTE,
        cliente=cliente_obj,
        titulo__iexact=titulo_limpio,
        activo=True,
    ).first()

    if existente is not None:
        if linea_obj is not None and existente.linea_servicio_id != linea_obj.pk:
            existente.linea_servicio = linea_obj
        if existente.tipo_documento != tipo_documento:
            existente.tipo_documento = tipo_documento
        existente.save()
        version = _crear_version_y_acceso(
            existente,
            usuario,
            archivo,
            nombre_limpio,
            comentario=comentario or "Nueva versión",
        )
        return existente, version

    documento = DocumentoRepositorio.objects.create(
        titulo=titulo_limpio[:200],
        categoria=DocumentoRepositorio.Categoria.PLANTILLA_CLIENTE,
        cliente=cliente_obj,
        tipo_documento=tipo_documento,
        linea_servicio=linea_obj,
        creado_por=usuario,
    )
    version = _crear_version_y_acceso(
        documento,
        usuario,
        archivo,
        nombre_limpio,
        comentario=comentario or "Versión inicial",
    )
    return documento, version


@transaction.atomic
def publicar_anonimizado(
    usuario,
    *,
    titulo,
    tipo_documento,
    archivo,
    confirmaciones=None,
    linea_servicio=None,
    comentario="",
):
    """Publica un ejemplo anonimizado tras comprobar los 4 ítems de la lista NDA (RF-35, HU-20)."""
    if not puede_publicar_anonimizado(usuario):
        raise PermissionDenied("Solo los seniors, el gerente y el admin pueden publicar ejemplos anonimizados.")

    verificacion = validar_verificacion_nda(confirmaciones, usuario)

    titulo_limpio = " ".join((titulo or "").split())
    if not titulo_limpio:
        raise ValidationError("Escriba el título del ejemplo anonimizado.")
    if tipo_documento not in DocumentoRepositorio.TipoDocumento.values:
        raise ValidationError("Elija un tipo de documento válido.")
    if archivo is None:
        raise ValidationError("Seleccione el archivo del ejemplo anonimizado.")

    linea_obj = _resolver_linea(linea_servicio)
    nombre_limpio = validar_archivo(archivo)

    existente = DocumentoRepositorio.objects.filter(
        categoria=DocumentoRepositorio.Categoria.EJEMPLO_ANONIMIZADO,
        titulo__iexact=titulo_limpio,
        activo=True,
    ).first()

    if existente is not None:
        if linea_obj is not None:
            existente.linea_servicio = linea_obj
        existente.tipo_documento = tipo_documento
        existente.save()
        version = _crear_version_y_acceso(
            existente,
            usuario,
            archivo,
            nombre_limpio,
            comentario=comentario or "Nueva versión anonimizada",
            verificacion=verificacion,
        )
        return existente, version

    documento = DocumentoRepositorio.objects.create(
        titulo=titulo_limpio[:200],
        categoria=DocumentoRepositorio.Categoria.EJEMPLO_ANONIMIZADO,
        cliente=None,
        tipo_documento=tipo_documento,
        linea_servicio=linea_obj,
        creado_por=usuario,
    )
    version = _crear_version_y_acceso(
        documento,
        usuario,
        archivo,
        nombre_limpio,
        comentario=comentario or "Publicación inicial anonimizada",
        verificacion=verificacion,
    )
    return documento, version


@transaction.atomic
def subir_nueva_version(
    documento,
    usuario,
    *,
    archivo,
    comentario="",
    confirmaciones=None,
    exigir_comentario=False,
):
    """Sube una nueva versión vigente a un documento existente del repositorio (`s2-documento.html`)."""
    if not puede_subir_version_o_restaurar(usuario, documento):
        raise PermissionDenied("No tiene permiso para cargar una nueva versión en este documento.")
    comentario_limpio = (comentario or "").strip()
    if exigir_comentario and not comentario_limpio:
        raise ValidationError("Escriba el comentario de la nueva versión.")
    if archivo is None:
        raise ValidationError("Seleccione el archivo de la nueva versión.")

    verificacion = {}
    if documento.es_anonimizado:
        if confirmaciones is not None:
            verificacion = validar_verificacion_nda(confirmaciones, usuario)
        else:
            vig = documento.version_vigente
            verificacion = dict(vig.verificacion_anonimizacion) if vig and vig.verificacion_anonimizacion else {
                "items_confirmados": list(CLAVES_NDA),
                "confirmado_por_id": usuario.pk,
                "confirmado_por": usuario.username,
                "confirmado_en": timezone.now().isoformat(),
            }

    nombre_limpio = validar_archivo(archivo)
    return _crear_version_y_acceso(
        documento,
        usuario,
        archivo,
        nombre_limpio,
        comentario=comentario_limpio,
        verificacion=verificacion,
    )


@transaction.atomic
def restaurar_version(version_anterior, usuario):
    """Restaura una versión histórica como vigente creando una NUEVA versión y registrando `RESTAURACION` (§7.9)."""
    documento = version_anterior.documento
    if not puede_subir_version_o_restaurar(usuario, documento):
        raise PermissionDenied("No tiene permiso para restaurar versiones de este documento.")
    if version_anterior.vigente:
        raise ValidationError(f"La v{version_anterior.numero} ya es la versión vigente.")
    try:
        with version_anterior.archivo.open("rb") as origen:
            contenido = ContentFile(origen.read(), name=version_anterior.nombre_original)
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise ValidationError(
            f"El archivo de la v{version_anterior.numero} no se encuentra en el servidor: no se puede restaurar."
        ) from exc

    return _crear_version_y_acceso(
        documento,
        usuario,
        contenido,
        version_anterior.nombre_original,
        comentario=f"Restaurada desde la v{version_anterior.numero}",
        verificacion=version_anterior.verificacion_anonimizacion,
        accion=RegistroAccesoDocumento.Accion.RESTAURACION,
    )


@transaction.atomic
def cambiar_estado_activo(documento, usuario, activo=False):
    """Da de baja (o reactiva) lógicamente un documento del repositorio: solo Gerente y Admin (§7.9)."""
    if not puede_dar_de_baja(usuario):
        raise PermissionDenied("Solo el gerente y el admin pueden dar de baja documentos del repositorio.")
    documento.activo = bool(activo)
    documento.save(update_fields=["activo"])
    return documento


@transaction.atomic
def registrar_descarga(version, usuario):
    """Verifica que el documento sea visible (404 si no) y registra el acceso de descarga (`DESCARGA`)."""
    if not documentos_visibles(usuario, incluir_inactivos=True).filter(pk=version.documento_id).exists():
        raise Http404("No existe ese documento del repositorio.")
    return RegistroAccesoDocumento.objects.create(
        version=version,
        usuario=usuario,
        accion=RegistroAccesoDocumento.Accion.DESCARGA,
    )
