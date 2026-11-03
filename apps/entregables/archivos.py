"""Validación común de los archivos subidos: extensión permitida, tamaño máximo y nombre saneado (SDD del Sprint 2, §5).

La usan los adjuntos de los entregables y la usarán la ficha de levantamiento (S2-H5) y el repositorio (S2-H9). Se extrajo
de adjuntos.py en el hito S2-H2 sin cambiar su comportamiento ni sus mensajes. Como tipos.py, no importa modelos ni otras
apps (solo Django y la biblioteca estándar): cualquier app puede usarla sin crear importaciones circulares.
"""
import os
import re
import unicodedata

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation, ValidationError
from django.utils.text import get_valid_filename

NOMBRE_MAX = 100


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
