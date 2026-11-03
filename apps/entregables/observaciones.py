"""Observaciones y revisiones (SDD del Sprint 2, RF-25 a RF-27, §7.2). Las reglas viven aquí, no en las vistas.

    [registrar] → PENDIENTE ──corregir──→ EN_CORRECCION ──confirmar──→ RESUELTA
                     ↑  └───────────resolver (Sprint 1, con solución)──────↗
                     └───────────rechazar──────────┘

- Registrar (una o varias en un envío): senior del entregable, gerente o admin. Si el entregable está en Revisión senior,
  vuelve a En proceso en la misma transacción mediante `servicios.mover` (la única puerta de cambio de estado), que crea
  las observaciones una sola vez.
- Corregir: el responsable de la observación o un senior del entregable (incluye gerente y admin); exige texto y admite
  como evidencia una versión de adjunto del mismo entregable.
- Confirmar o rechazar: senior del entregable, gerente o admin. RESUELTA exige acción correctiva y registra quién la revisó
  y cuándo.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.alertas.models import Notificacion

from . import adjuntos, servicios
from .models import Adjunto, Entregable, Observacion
from .visibilidad import entregables_visibles, es_senior_del_entregable

E = Entregable.Estado
O = Observacion.Estado

DETALLE_MAX = 255


def _historial(entregable, usuario, detalle):
    adjuntos.registrar_en_historial(entregable, usuario, detalle[:DETALLE_MAX])


def puede_registrar(usuario, entregable):
    return es_senior_del_entregable(usuario, entregable)


def puede_corregir(usuario, observacion, entregable=None):
    entregable = entregable or observacion.entregable
    return usuario.pk == observacion.responsable_id or es_senior_del_entregable(usuario, entregable)


def puede_revisar(usuario, entregable):
    return es_senior_del_entregable(usuario, entregable)


# ------------------------------------------------------------------ registrar

def registrar(entregable, usuario, items):
    """Registra una o varias observaciones (lista de dicts con tipo_error, descripcion y responsable opcional).

    Si el entregable está en Revisión senior lo devuelve a En proceso con `servicios.mover` (que crea las observaciones y
    avisa al junior); si no, las crea y avisa al junior asignado (tipo OBSERVACION, con el código). Devuelve
    (observaciones creadas, devuelto: bool).
    """
    if not puede_registrar(usuario, entregable):
        raise PermissionDenied("Solo el senior del entregable, el gerente o el admin registran observaciones.")
    items = servicios.validar_observaciones(entregable, items, al_devolver=False)
    with transaction.atomic():
        if entregable.estado == E.VERIFICACION_SENIOR:
            antes = set(entregable.observaciones.values_list("pk", flat=True))
            servicios.mover(entregable, E.EN_PROCESO, usuario, observaciones=items)
            creadas = list(entregable.observaciones.exclude(pk__in=antes))
            return creadas, True
        creadas = servicios.crear_observaciones(entregable, usuario, items)
        n = len(creadas)
        tipos = ", ".join(dict.fromkeys(o.get_tipo_error_display() for o in creadas))
        _historial(entregable, usuario,
                   f"Registró una observación ({tipos})" if n == 1 else f"Registró {n} observaciones ({tipos})")
        Notificacion.objects.create(
            usuario=entregable.junior_asignado, entregable=entregable, tipo=Notificacion.Tipo.OBSERVACION,
            mensaje=servicios.texto_observaciones(entregable, n), enlace=servicios.enlace_observaciones(entregable),
        )
    return creadas, False


# ------------------------------------------------------------------ corregir

def texto_correccion(observacion, entregable):
    return (f"Se registró la corrección de una observación ({observacion.get_tipo_error_display()}) en "
            f"{entregable.referencia}; espera su revisión.")


def texto_rechazo(observacion, entregable):
    return (f"Se rechazó la corrección de la observación ({observacion.get_tipo_error_display()}) en "
            f"{entregable.referencia}: vuelve a «{O.PENDIENTE.label}».")


def evidencias_posibles(entregable):
    """Versiones de adjunto del entregable que pueden servir de evidencia."""
    return Adjunto.objects.filter(entregable=entregable).order_by("tipo", "-version")


def corregir(observacion, usuario, accion_correctiva, evidencia=None):
    """PENDIENTE → EN_CORRECCION. Exige el texto de la acción correctiva; la evidencia es opcional (un Adjunto o su id)."""
    entregable = observacion.entregable
    if not puede_corregir(usuario, observacion, entregable):
        raise PermissionDenied("Solo el responsable de la observación o un senior del entregable registran la corrección.")
    if observacion.estado != O.PENDIENTE:
        raise ValidationError(
            f"Solo se registra la corrección de una observación «{O.PENDIENTE.label}»; esta está "
            f"«{observacion.get_estado_display()}»."
        )
    texto = (accion_correctiva or "").strip()
    if not texto:
        raise ValidationError("Escriba la acción correctiva: qué se corrigió.")
    adjunto = None
    if evidencia not in (None, ""):
        adjunto_id = evidencia.pk if isinstance(evidencia, Adjunto) else evidencia
        try:
            adjunto = Adjunto.objects.get(pk=int(adjunto_id), entregable_id=entregable.pk)
        except (TypeError, ValueError, OverflowError, Adjunto.DoesNotExist):
            raise ValidationError("La evidencia debe ser una versión de un adjunto de este mismo entregable.")
    with transaction.atomic():
        observacion.estado = O.EN_CORRECCION
        observacion.solucion = texto
        observacion.evidencia = adjunto
        observacion.corregida_por, observacion.corregida_en = usuario, timezone.now()
        observacion.save()
        _historial(entregable, usuario,
                   f"Registró la corrección de una observación ({observacion.get_tipo_error_display()})")
        if entregable.senior_revisor_id != usuario.pk:
            Notificacion.objects.create(
                usuario=entregable.senior_revisor, entregable=entregable, tipo=Notificacion.Tipo.CORRECCION,
                mensaje=texto_correccion(observacion, entregable)[:255], enlace=servicios.enlace_observaciones(entregable),
            )
    return observacion


# ------------------------------------------------------------------ revisar

def confirmar(observacion, usuario):
    """EN_CORRECCION → RESUELTA (HU-12 criterio 4): queda quién la revisó y cuándo."""
    entregable = observacion.entregable
    if not puede_revisar(usuario, entregable):
        raise PermissionDenied("Solo el senior del entregable, el gerente o el admin confirman una corrección.")
    if observacion.estado != O.EN_CORRECCION:
        raise ValidationError(f"Solo se confirma una observación «{O.EN_CORRECCION.label}»; esta está "
                              f"«{observacion.get_estado_display()}».")
    if not observacion.solucion.strip():
        raise ValidationError("No se puede resolver una observación sin acción correctiva.")
    with transaction.atomic():
        _resolver(observacion, usuario)
        _historial(entregable, usuario,
                   f"Confirmó la corrección de una observación ({observacion.get_tipo_error_display()}): resuelta")
    return observacion


def rechazar(observacion, usuario, motivo=""):
    """EN_CORRECCION → PENDIENTE. Avisa al responsable. La corrección rechazada (texto, autor y fecha) se conserva."""
    entregable = observacion.entregable
    if not puede_revisar(usuario, entregable):
        raise PermissionDenied("Solo el senior del entregable, el gerente o el admin rechazan una corrección.")
    if observacion.estado != O.EN_CORRECCION:
        raise ValidationError(f"Solo se rechaza una observación «{O.EN_CORRECCION.label}»; esta está "
                              f"«{observacion.get_estado_display()}».")
    motivo = (motivo or "").strip()
    with transaction.atomic():
        observacion.estado = O.PENDIENTE
        observacion.save()
        detalle = f"Rechazó la corrección de una observación ({observacion.get_tipo_error_display()})"
        _historial(entregable, usuario, f"{detalle}: {motivo}" if motivo else detalle)
        if observacion.responsable_id and observacion.responsable_id != usuario.pk:
            Notificacion.objects.create(
                usuario=observacion.responsable, entregable=entregable, tipo=Notificacion.Tipo.OBSERVACION,
                mensaje=texto_rechazo(observacion, entregable)[:255], enlace=servicios.enlace_observaciones(entregable),
            )
    return observacion


def resolver(observacion, usuario, solucion):
    """Resolución directa del Sprint 1 (`/observaciones/<id>/resolver/`): PENDIENTE o EN_CORRECCION → RESUELTA con la
    solución escrita (la acción correctiva). Senior del entregable, gerente o admin."""
    entregable = observacion.entregable
    if not puede_revisar(usuario, entregable):
        raise PermissionDenied("No tiene permiso para resolver esta observación.")
    texto = (solucion or "").strip()
    if not texto:
        raise ValidationError("Escriba la solución aplicada para marcar la observación como resuelta.")
    if observacion.estado == O.RESUELTA:
        raise ValidationError("Esta observación ya está resuelta.")
    with transaction.atomic():
        observacion.solucion = texto
        _resolver(observacion, usuario)
        _historial(entregable, usuario, f"Resolvió una observación ({observacion.get_tipo_error_display()})")
    return observacion


def _resolver(observacion, usuario):
    observacion.estado = O.RESUELTA
    observacion.revisada_por, observacion.resuelta_en = usuario, timezone.now()
    observacion.save()


# ------------------------------------------------------------------ historial (RF-27)

def visibles(usuario):
    """Observaciones de los entregables que el usuario puede ver (los filtros solo reducen este conjunto)."""
    return Observacion.objects.filter(entregable__in=entregables_visibles(usuario).values("pk"))
