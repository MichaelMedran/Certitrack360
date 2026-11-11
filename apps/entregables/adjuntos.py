"""Adjuntos de los entregables: validación, versionado, permisos y registro en el historial."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max, Q

# La validación de archivos es común a otras apps (ficha de levantamiento, repositorio) y vive en archivos.py. Sus nombres
# se siguen ofreciendo aquí para quienes ya los usaban desde adjuntos (formularios, vistas y pruebas).
from .archivos import NOMBRE_MAX, extensiones_permitidas, sanear_nombre, tamano_maximo_bytes, validar_archivo  # noqa: F401
from .models import Adjunto, Entregable, HistorialEstado
from .tipos import TIPOS_GENERADOS, TipoAdjunto
from .visibilidad import es_elaborador_del_entregable, es_senior_del_entregable

# El junior o responsable de apoyo solo puede subir mientras el entregable está en estas columnas.
ESTADOS_INICIALES = (Entregable.Estado.A_REALIZAR, Entregable.Estado.EN_PROCESO)


def etiqueta_tipo(codigo):
    return str(dict(TipoAdjunto.choices).get(codigo, codigo))


def puede_subir(usuario, entregable):
    """Junior asignado o apoyo activo (solo en estados iniciales), senior del entregable, gerente y admin."""
    if usuario.es_gerente_o_admin or es_senior_del_entregable(usuario, entregable):
        return True
    return es_elaborador_del_entregable(usuario, entregable) and entregable.estado in ESTADOS_INICIALES


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


def puede_restaurar(usuario, entregable):
    """Senior del entregable, gerente y admin (SDD del Sprint 2, §8)."""
    return es_senior_del_entregable(usuario, entregable)


def vigente(entregable, tipo):
    """La versión vigente de un tipo: la de número más alto que no fue eliminada (o None si no hay ninguna)."""
    return Adjunto.objects.filter(entregable=entregable, tipo=tipo).order_by("-version").first()


@transaction.atomic
def crear_adjunto(entregable, usuario, archivo, tipo, comentario="", restaurado_desde=None, detalle=None, bloqueado=False):
    """Valida, asigna la versión siguiente del tipo y registra el evento. No revisa permisos (ver `subir`).

    `restaurado_desde` y `detalle` los usa `restaurar`; `bloqueado` lo usan el cargo y el acta, que nacen bloqueados.
    """
    if tipo not in TipoAdjunto.values:
        raise ValidationError("Elija el tipo de adjunto.")
    nombre = validar_archivo(archivo)
    # Bloquea el entregable para que dos subidas simultáneas no obtengan la misma versión.
    Entregable.objects.select_for_update().get(pk=entregable.pk)
    ultima = Adjunto.objects.filter(entregable=entregable, tipo=tipo).aggregate(m=Max("version"))["m"] or 0
    archivo.name = nombre
    adjunto = Adjunto.objects.create(
        entregable=entregable, archivo=archivo, nombre_original=nombre, tipo=tipo, version=ultima + 1,
        comentario=(comentario or "").strip()[:255], subido_por=usuario, bloqueado=bloqueado,
        restaurado_desde=restaurado_desde,
    )
    if callable(detalle):
        detalle = detalle(adjunto)
    registrar_en_historial(
        entregable, usuario, detalle or f"Subió adjunto: {etiqueta_tipo(tipo)} v{adjunto.version} ({nombre})"
    )
    return adjunto


def subir(entregable, usuario, archivo, tipo, comentario=""):
    if not puede_subir(usuario, entregable):
        raise PermissionDenied("No tiene permiso para subir adjuntos a este entregable en su estado actual.")
    if tipo in TIPOS_GENERADOS:  # el cargo y el acta nacen del registro de la entrega, no de la subida
        raise ValidationError(f"«{etiqueta_tipo(tipo)}» se registra con la entrega del entregable, no como adjunto suelto.")
    return crear_adjunto(entregable, usuario, archivo, tipo, comentario)


@transaction.atomic
def restaurar(adjunto, usuario):
    """Restaura una versión anterior como vigente (RF-28): crea una versión NUEVA que copia su archivo, con
    `restaurado_desde` y el comentario «Restaurada desde la vN». Nunca reescribe una versión. Queda en el historial.

    Senior del entregable, gerente y admin. Solo se restauran tipos de documento versionables (no el cargo ni el acta) y
    solo una versión que ya no es la vigente.
    """
    entregable = adjunto.entregable
    if not puede_restaurar(usuario, entregable):
        raise PermissionDenied("Solo el senior del entregable, el gerente y el admin restauran versiones.")
    if adjunto.tipo in TIPOS_GENERADOS:
        raise ValidationError(f"«{etiqueta_tipo(adjunto.tipo)}» no se restaura: es parte del registro de la entrega.")
    actual = vigente(entregable, adjunto.tipo)
    if actual is None or actual.pk == adjunto.pk:
        raise ValidationError(f"La v{adjunto.version} de «{etiqueta_tipo(adjunto.tipo)}» ya es la versión vigente.")
    try:
        with adjunto.archivo.open("rb") as origen:
            contenido = ContentFile(origen.read(), name=adjunto.nombre_original)
    except (FileNotFoundError, ValueError, OSError):
        raise ValidationError(f"El archivo de la v{adjunto.version} no se encuentra en el servidor: no se puede restaurar.")
    # El historial dice qué versión se restauró y cuál nació de ella.
    return crear_adjunto(
        entregable, usuario, contenido, adjunto.tipo, comentario=f"Restaurada desde la v{adjunto.version}",
        restaurado_desde=adjunto,
        detalle=lambda nueva: (f"Restauró {etiqueta_tipo(adjunto.tipo)} v{adjunto.version} como vigente "
                               f"(nueva v{nueva.version}, {nueva.nombre_original})"),
    )


MOTIVO_BLOQUEO = (
    "Esta versión está bloqueada: es parte de una entrega al cliente (versión enviada, cargo o acta) y no se puede eliminar."
)


def esta_bloqueado(adjunto):
    """Bloqueado en la base de datos (no solo en la instancia en memoria) o referenciado por una entrega: la versión enviada,
    el cargo y el acta no se eliminan."""
    from .models import Entrega

    return (
        adjunto.bloqueado
        or Adjunto.objects.filter(pk=adjunto.pk, bloqueado=True).exists()
        or Entrega.objects.filter(
            Q(cargo_id=adjunto.pk) | Q(version_enviada_id=adjunto.pk) | Q(acta_id=adjunto.pk)
        ).exists()
    )


@transaction.atomic
def eliminar(adjunto, usuario):
    """Solo gerente y admin, y nunca una versión bloqueada. El archivo se borra del disco al confirmarse la transacción
    (ver signals)."""
    if not puede_eliminar(usuario):
        raise PermissionDenied("Solo el gerente y el admin pueden eliminar adjuntos.")
    if esta_bloqueado(adjunto):
        raise PermissionDenied(MOTIVO_BLOQUEO)
    registrar_en_historial(
        adjunto.entregable, usuario,
        f"Eliminó adjunto: {etiqueta_tipo(adjunto.tipo)} v{adjunto.version} ({adjunto.nombre_original})",
    )
    adjunto.delete()
