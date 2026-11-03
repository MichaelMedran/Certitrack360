"""Adjuntos de los entregables: validación, versionado, permisos y registro en el historial."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max

# La validación de archivos es común a otras apps (ficha de levantamiento, repositorio) y vive en archivos.py. Sus nombres
# se siguen ofreciendo aquí para quienes ya los usaban desde adjuntos (formularios, vistas y pruebas).
from .archivos import NOMBRE_MAX, extensiones_permitidas, sanear_nombre, tamano_maximo_bytes, validar_archivo  # noqa: F401
from .models import Adjunto, Entregable, HistorialEstado
from .tipos import TipoAdjunto
from .visibilidad import es_senior_del_entregable

# El junior solo puede subir mientras el entregable está en estas columnas.
ESTADOS_INICIALES = (Entregable.Estado.A_REALIZAR, Entregable.Estado.EN_PROCESO)


def etiqueta_tipo(codigo):
    return str(dict(TipoAdjunto.choices).get(codigo, codigo))


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
