"""Adjuntos de los entregables: validación, versionado, permisos y registro en el historial."""
import os
import re
import unicodedata

from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousFileOperation, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils.text import get_valid_filename

from .models import Adjunto, Entregable, HistorialEstado
from .tipos import TipoAdjunto
from .visibilidad import es_senior_del_entregable

# El junior solo puede subir mientras el entregable está en estas columnas.
ESTADOS_INICIALES = (Entregable.Estado.A_REALIZAR, Entregable.Estado.EN_PROCESO)
NOMBRE_MAX = 100


def etiqueta_tipo(codigo):
    return str(dict(TipoAdjunto.choices).get(codigo, codigo))


def extensiones_permitidas():
    return [e.lower().lstrip(".") for e in settings.ALLOWED_UPLOAD_EXTENSIONS]


def tamano_maximo_bytes():
    return int(settings.MEDIA_MAX_UPLOAD_MB * 1024 * 1024)


def sanear_nombre(nombre):
    """Deja solo el nombre del archivo: sin carpetas, sin caracteres de control ni símbolos raros, y con largo acotado."""
    nombre = (nombre or "").replace("\\", "/").split("/")[-1]
    nombre = unicodedata.normalize("NFC", nombre)
    nombre = re.sub(r"[\x00-\x1f\x7f]", "", nombre)
    try:
        nombre = get_valid_filename(nombre)
    except SuspiciousFileOperation:
        nombre = ""
    nombre = nombre.lstrip(".")  # sin archivos ocultos
    base, ext = os.path.splitext(nombre)
    if len(nombre) > NOMBRE_MAX:
        nombre = base[: max(1, NOMBRE_MAX - len(ext))] + ext
    return nombre or "archivo"


def validar_archivo(archivo):
    """Devuelve el nombre saneado, o lanza ValidationError con un mensaje que dice qué corregir."""
    nombre = sanear_nombre(getattr(archivo, "name", ""))
    extension = os.path.splitext(nombre)[1].lower().lstrip(".")
    permitidas = extensiones_permitidas()
    if extension not in permitidas:
        raise ValidationError(
            f"El archivo «{nombre}» no es de un tipo permitido. Formatos permitidos: {', '.join(permitidas)}."
        )
    if archivo.size == 0:
        raise ValidationError(f"El archivo «{nombre}» está vacío.")
    if archivo.size > tamano_maximo_bytes():
        pesa = f"{archivo.size / (1024 * 1024):.1f}".replace(".", ",")
        raise ValidationError(
            f"El archivo «{nombre}» pesa {pesa} MB y el máximo permitido es {settings.MEDIA_MAX_UPLOAD_MB:g} MB."
        )
    return nombre


def puede_subir(usuario, entregable):
    """Junior asignado (solo en estados iniciales), senior del entregable, gerente y admin."""
    if usuario.es_gerente_o_admin:
        return True
    if usuario.es_senior:
        return es_senior_del_entregable(usuario, entregable)
    return usuario.pk == entregable.junior_asignado_id and entregable.estado in ESTADOS_INICIALES


def puede_eliminar(usuario):
    return usuario.es_gerente_o_admin


def registrar_en_historial(entregable, usuario, detalle):
    """Deja constancia en el historial sin cambiar de estado (estado anterior = estado nuevo = el actual)."""
    HistorialEstado.objects.create(
        entregable=entregable, estado_anterior=entregable.estado, estado_nuevo=entregable.estado,
        usuario=usuario, detalle=detalle[:255],
    )


def faltantes_requeridos(entregable):
    """Códigos de los tipos de adjunto que exige la plantilla y que el entregable aún no tiene (en orden)."""
    requeridos = dict.fromkeys(t for t in entregable.plantilla.adjuntos_requeridos if t)
    presentes = set(entregable.adjuntos.values_list("tipo", flat=True))
    return [t for t in requeridos if t not in presentes]


@transaction.atomic
def crear_adjunto(entregable, usuario, archivo, tipo, comentario=""):
    """Valida, asigna la versión siguiente del tipo y registra el evento. No revisa permisos (ver `subir`)."""
    if tipo not in TipoAdjunto.values:
        raise ValidationError("Elija el tipo de adjunto.")
    nombre = validar_archivo(archivo)
    # Bloquea el entregable para que dos subidas simultáneas no obtengan la misma versión.
    Entregable.objects.select_for_update().get(pk=entregable.pk)
    ultima = Adjunto.objects.filter(entregable=entregable, tipo=tipo).aggregate(m=Max("version"))["m"] or 0
    archivo.name = nombre
    adjunto = Adjunto.objects.create(
        entregable=entregable, archivo=archivo, nombre_original=nombre, tipo=tipo, version=ultima + 1,
        comentario=(comentario or "").strip()[:255], subido_por=usuario,
    )
    registrar_en_historial(
        entregable, usuario, f"Subió adjunto: {etiqueta_tipo(tipo)} v{adjunto.version} ({nombre})"
    )
    return adjunto


def subir(entregable, usuario, archivo, tipo, comentario=""):
    if not puede_subir(usuario, entregable):
        raise PermissionDenied("No tiene permiso para subir adjuntos a este entregable en su estado actual.")
    return crear_adjunto(entregable, usuario, archivo, tipo, comentario)


@transaction.atomic
def eliminar(adjunto, usuario):
    """Solo gerente y admin. El archivo se borra del disco al confirmarse la transacción (ver signals)."""
    if not puede_eliminar(usuario):
        raise PermissionDenied("Solo el gerente y el admin pueden eliminar adjuntos.")
    registrar_en_historial(
        adjunto.entregable, usuario,
        f"Eliminó adjunto: {etiqueta_tipo(adjunto.tipo)} v{adjunto.version} ({adjunto.nombre_original})",
    )
    adjunto.delete()
