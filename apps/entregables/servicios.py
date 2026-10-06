"""Máquina de estados del tablero. Toda transición se valida aquí, en el servidor."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.alertas.models import Notificacion

from . import adjuntos
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


def datos_faltantes(entregable):
    """Etiquetas de los campos obligatorios de la plantilla que el entregable no tiene completos."""
    return [
        c["etiqueta"]
        for c in entregable.plantilla.campos_requeridos
        if str(entregable.datos.get(c["nombre"], "")).strip() == ""
    ]


def requisitos_para_verificacion(entregable):
    """Mensaje con todo lo que falta para pasar a Verificación senior, o None si ya se puede (SDD §10.1)."""
    partes, ayudas = [], []
    datos = datos_faltantes(entregable)
    if datos:
        partes.append("los datos obligatorios (" + ", ".join(f"«{d}»" for d in datos) + ")")
        ayudas.append("Un gerente o admin puede completar los datos.")
    adjuntos_faltan = adjuntos.faltantes_requeridos(entregable)
    if adjuntos_faltan:
        partes.append("los adjuntos requeridos (" + ", ".join(f"«{adjuntos.etiqueta_tipo(t)}»" for t in adjuntos_faltan) + ")")
        ayudas.append("Suba los adjuntos en el detalle del entregable.")
    if not partes:
        return None
    return f"No se puede enviar a verificación: faltan {' y '.join(partes)}. {' '.join(ayudas)}"


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

    if nuevo_estado == E.VERIFICACION_SENIOR:
        faltante = requisitos_para_verificacion(entregable)
        if faltante:
            raise ValidationError(faltante)

    devuelve = clave == (E.VERIFICACION_SENIOR, E.EN_PROCESO)
    if devuelve:
        if not tipo_error or tipo_error not in TipoError.values:
            raise ValidationError("Para devolver el entregable debe indicar el tipo de error.", code="observacion_requerida")
        if not descripcion.strip():
            raise ValidationError("Para devolver el entregable debe describir la observación.", code="observacion_requerida")

    with transaction.atomic():
        entregable.estado = nuevo_estado
        entregable.save(update_fields=["estado", "actualizado_en"])
        HistorialEstado.objects.create(
            entregable=entregable, estado_anterior=actual, estado_nuevo=nuevo_estado, usuario=usuario,
            detalle=f"Devuelto con observación ({TipoError(tipo_error).label})" if devuelve else "",
        )
        if nuevo_estado == E.VERIFICACION_SENIOR and entregable.senior_revisor_id != usuario.pk:
            Notificacion.objects.create(
                usuario=entregable.senior_revisor, entregable=entregable, tipo=Notificacion.Tipo.VERIFICACION,
                mensaje=f"«{entregable.titulo}» está en verificación y espera su revisión.",
            )
        if devuelve:
            Observacion.objects.create(
                entregable=entregable, autor=usuario, tipo_error=tipo_error, descripcion=descripcion.strip()
            )
            Notificacion.objects.create(
                usuario=entregable.junior_asignado, entregable=entregable, tipo=Notificacion.Tipo.OBSERVACION,
                mensaje=f"«{entregable.titulo}» fue devuelto con una observación.",
            )
        if nuevo_estado == E.HECHO:
            # Fase 2: las observaciones resueltas de un entregable cerrado se convierten en lecciones aprendidas.
            from apps.conocimiento.servicios import generar_lecciones

            generar_lecciones(entregable)
    return entregable


def registrar_creacion(entregable, usuario):
    """Primer registro del historial y aviso de asignación al junior."""
    HistorialEstado.objects.create(
        entregable=entregable, estado_anterior="", estado_nuevo=entregable.estado, usuario=usuario,
        detalle="Entregable creado",
    )
    Notificacion.objects.create(
        usuario=entregable.junior_asignado, entregable=entregable, tipo=Notificacion.Tipo.ASIGNACION,
        mensaje=f"Se le asignó «{entregable.titulo}» (vence el {entregable.plazo:%d/%m/%Y}).",
    )
