"""Máquina de estados del tablero. Toda transición se valida aquí, en el servidor."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.alertas.models import Notificacion

from .models import Entregable, HistorialEstado, Observacion, TipoError
from .visibilidad import es_senior_del_entregable

E = Entregable.Estado

# (estado origen, estado destino) -> quién puede: "junior" o "senior"
TRANSICIONES = {
    (E.A_REALIZAR, E.EN_PROCESO): "junior",
    (E.EN_PROCESO, E.VERIFICACION_SENIOR): "junior",
    (E.VERIFICACION_SENIOR, E.LISTO_PARA_ENTREGA): "senior",
    (E.VERIFICACION_SENIOR, E.EN_PROCESO): "senior",
    (E.LISTO_PARA_ENTREGA, E.HECHO): "senior",
}


def mover(entregable, nuevo_estado, usuario, tipo_error=None, descripcion=""):
    """Cambia el estado y registra el historial. Lanza ValidationError o PermissionDenied."""
    actual = entregable.estado
    clave = (actual, nuevo_estado)
    if clave not in TRANSICIONES:
        raise ValidationError("Ese movimiento no está permitido en el flujo de trabajo.")

    exigido = TRANSICIONES[clave]
    if exigido == "junior":
        autorizado = usuario.pk == entregable.junior_asignado_id or es_senior_del_entregable(usuario, entregable)
    else:
        autorizado = es_senior_del_entregable(usuario, entregable)
    if not autorizado:
        raise PermissionDenied("No tiene permiso para realizar este movimiento.")

    devuelve = clave == (E.VERIFICACION_SENIOR, E.EN_PROCESO)
    if devuelve:
        if not tipo_error or tipo_error not in TipoError.values:
            raise ValidationError("Para devolver el entregable debe indicar el tipo de error.")
        if not descripcion.strip():
            raise ValidationError("Para devolver el entregable debe describir la observación.")

    with transaction.atomic():
        entregable.estado = nuevo_estado
        entregable.save(update_fields=["estado", "actualizado_en"])
        HistorialEstado.objects.create(
            entregable=entregable, estado_anterior=actual, estado_nuevo=nuevo_estado, usuario=usuario
        )
        if devuelve:
            Observacion.objects.create(
                entregable=entregable, autor=usuario, tipo_error=tipo_error, descripcion=descripcion.strip()
            )
            Notificacion.objects.create(
                usuario=entregable.junior_asignado, entregable=entregable, tipo=Notificacion.Tipo.OBSERVACION,
                mensaje=f"«{entregable.titulo}» fue devuelto con una observación.",
            )
    return entregable


def registrar_creacion(entregable, usuario):
    """Primer registro del historial y aviso de asignación al junior."""
    HistorialEstado.objects.create(
        entregable=entregable, estado_anterior="", estado_nuevo=entregable.estado, usuario=usuario
    )
    Notificacion.objects.create(
        usuario=entregable.junior_asignado, entregable=entregable, tipo=Notificacion.Tipo.ASIGNACION,
        mensaje=f"Se le asignó «{entregable.titulo}» (vence el {entregable.plazo:%d/%m/%Y}).",
    )
