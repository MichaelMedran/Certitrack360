"""Máquina de estados del tablero. Toda transición se valida aquí, en el servidor."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse

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


def texto_asignacion(entregable):
    return f"Se le asignó {entregable.referencia} (vence el {entregable.plazo:%d/%m/%Y})."


def texto_en_revision(entregable):
    return f"{entregable.referencia} pasó a «{E.VERIFICACION_SENIOR.label}» y espera su revisión."


def texto_devuelto(entregable):
    return f"{entregable.referencia} fue devuelto con una observación."


def texto_devuelto_varias(entregable, n):
    return f"{entregable.referencia} fue devuelto con {n} observaciones."


def texto_observacion(entregable):
    return f"Nueva observación en {entregable.referencia}."


def texto_observaciones(entregable, n):
    """Aviso al junior al registrar observaciones (RF-26): lleva el código del entregable."""
    return texto_observacion(entregable) if n == 1 else f"{n} observaciones nuevas en {entregable.referencia}."


def enlace_observaciones(entregable):
    """Ruta interna a la sección Observaciones del detalle (destino de los avisos de observaciones)."""
    return reverse("entregable_detalle", args=[entregable.pk]) + "#observaciones"


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def _tipos(observaciones):
    """«Formato», «Contenido»: los tipos de error, sin repetir y en el orden en que aparecen."""
    return ", ".join(f"«{t}»" for t in dict.fromkeys(o.get_tipo_error_display() for o in observaciones))


def observaciones_que_impiden(entregable, nuevo_estado):
    """Mensaje si las observaciones impiden el paso (SDD del Sprint 2, §7.1), o None.

    - A Revisión senior no se pasa con observaciones PENDIENTE (las que están En corrección sí pueden ir a revisión).
    - A Aprobado no se pasa con observaciones abiertas (Pendiente o En corrección).
    """
    if nuevo_estado == E.VERIFICACION_SENIOR:
        pendientes = list(entregable.observaciones.pendientes())
        if pendientes:
            n = len(pendientes)
            return (f"No se puede enviar a revisión: hay {_plural(n, 'observación pendiente', 'observaciones pendientes')} "
                    f"({_tipos(pendientes)}). Registre la acción correctiva en la sección Observaciones.")
    elif nuevo_estado == E.LISTO_PARA_ENTREGA:
        abiertas = list(entregable.observaciones.abiertas())
        if abiertas:
            n = len(abiertas)
            detalle = ", ".join(f"«{o.get_tipo_error_display()}» {o.get_estado_display().lower()}" for o in abiertas)
            return (f"No se puede aprobar: hay {_plural(n, 'observación abierta', 'observaciones abiertas')} ({detalle}). "
                    "Confirme las correcciones o resuelva las observaciones en la sección Observaciones.")
    return None


def responsables_posibles(entregable):
    """Quién puede ser responsable de una observación: el junior asignado (por defecto) o un senior del entregable."""
    ids = [entregable.junior_asignado_id, entregable.senior_revisor_id, entregable.contrato.senior_responsable_id]
    from apps.cuentas.models import Usuario

    por_id = Usuario.objects.in_bulk([i for i in ids if i])
    return [por_id[i] for i in dict.fromkeys(ids) if i in por_id]


def validar_observaciones(entregable, items, al_devolver=True):
    """Valida una lista de observaciones nuevas: dicts con tipo_error, descripcion y responsable (Usuario o None).

    Devuelve la lista normalizada (descripción sin espacios sobrantes y responsable por defecto, el junior asignado).
    Lanza ValidationError; al devolver usa los mensajes y el código del Sprint 1 («observacion_requerida»), que el tablero
    usa para abrir el diálogo de devolución.
    """
    if al_devolver:
        falta_tipo = "Para devolver el entregable debe indicar el tipo de error."
        falta_descripcion = "Para devolver el entregable debe describir la observación."
    else:
        falta_tipo, falta_descripcion = "Elija el tipo de error.", "Describa la observación."
    if not items:
        raise ValidationError(falta_tipo, code="observacion_requerida")
    permitidos = {u.pk for u in responsables_posibles(entregable)}
    varias = len(items) > 1
    salida = []
    for n, item in enumerate(items, start=1):
        prefijo = f"Observación {n}: " if varias else ""
        tipo, descripcion = item.get("tipo_error"), (item.get("descripcion") or "").strip()
        if not tipo or tipo not in TipoError.values:
            raise ValidationError(prefijo + falta_tipo, code="observacion_requerida")
        if not descripcion:
            raise ValidationError(prefijo + falta_descripcion, code="observacion_requerida")
        responsable = item.get("responsable")
        if responsable is None:
            responsable = entregable.junior_asignado
        elif getattr(responsable, "pk", None) not in permitidos:
            raise ValidationError(prefijo + "El responsable debe ser el junior asignado o un senior del entregable.",
                                  code="responsable_no_valido")
        salida.append({"tipo_error": tipo, "descripcion": descripcion, "responsable": responsable})
    return salida


def crear_observaciones(entregable, usuario, items):
    """Crea las observaciones ya validadas (en la transacción de quien llama) y devuelve la lista."""
    return [
        Observacion.objects.create(
            entregable=entregable, autor=usuario, tipo_error=i["tipo_error"], descripcion=i["descripcion"],
            responsable=i["responsable"],
        )
        for i in items
    ]


def requisitos_para_verificacion(entregable):
    """Mensaje con todo lo que falta para pasar a Revisión senior (VERIFICACION_SENIOR), o None si ya se puede (SDD §10.1)."""
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


def mover(entregable, nuevo_estado, usuario, tipo_error=None, descripcion="", observaciones=None):
    """Cambia el estado y registra el historial. Lanza ValidationError o PermissionDenied.

    Es la única puerta para cambiar de estado. Al devolver (Revisión senior → En proceso) exige al menos una observación:
    la del Sprint 1 (`tipo_error` y `descripcion`) o varias a la vez (`observaciones`: lista de dicts con tipo_error,
    descripcion y responsable opcional), que se crean aquí mismo, en la misma transacción, una sola vez.
    """
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

    motivos = []
    if nuevo_estado == E.VERIFICACION_SENIOR:
        motivos.append(requisitos_para_verificacion(entregable))
    motivos.append(observaciones_que_impiden(entregable, nuevo_estado))  # condiciones nuevas del Sprint 2 (§7.1)
    motivos = [m for m in motivos if m]
    if motivos:
        raise ValidationError(motivos[0] if len(motivos) == 1 else motivos)

    devuelve = clave == (E.VERIFICACION_SENIOR, E.EN_PROCESO)
    if devuelve:
        if observaciones is None:  # devolución del Sprint 1: una observación
            observaciones = [{"tipo_error": tipo_error, "descripcion": descripcion or ""}] if (tipo_error or descripcion) else []
        observaciones = validar_observaciones(entregable, observaciones)

    with transaction.atomic():
        entregable.estado = nuevo_estado
        entregable.save(update_fields=["estado", "actualizado_en"])
        if devuelve:
            n = len(observaciones)
            detalle = (f"Devuelto con observación ({TipoError(observaciones[0]['tipo_error']).label})" if n == 1
                       else f"Devuelto con {n} observaciones ("
                            + ", ".join(dict.fromkeys(TipoError(o["tipo_error"]).label for o in observaciones)) + ")")
        else:
            detalle = ""
        HistorialEstado.objects.create(
            entregable=entregable, estado_anterior=actual, estado_nuevo=nuevo_estado, usuario=usuario, detalle=detalle[:255],
        )
        if nuevo_estado == E.VERIFICACION_SENIOR and entregable.senior_revisor_id != usuario.pk:
            Notificacion.objects.create(
                usuario=entregable.senior_revisor, entregable=entregable, tipo=Notificacion.Tipo.VERIFICACION,
                mensaje=texto_en_revision(entregable),
            )
        if devuelve:
            # Queda «Con correcciones pendientes»: aviso inmediato al junior con el código (RF-22 y RF-26).
            crear_observaciones(entregable, usuario, observaciones)
            Notificacion.objects.create(
                usuario=entregable.junior_asignado, entregable=entregable, tipo=Notificacion.Tipo.OBSERVACION,
                mensaje=texto_devuelto(entregable) if n == 1 else texto_devuelto_varias(entregable, n),
                enlace=enlace_observaciones(entregable),
            )
        if nuevo_estado == E.HECHO:
            # Fase 2: las observaciones resueltas de un entregable cerrado se convierten en lecciones aprendidas.
            from apps.conocimiento.servicios import generar_lecciones

            generar_lecciones(entregable)
    return entregable


def registrar_creacion(entregable, usuario):
    """Primer registro del historial y aviso de asignación al junior (con el código del entregable)."""
    HistorialEstado.objects.create(
        entregable=entregable, estado_anterior="", estado_nuevo=entregable.estado, usuario=usuario,
        detalle="Entregable creado",
    )
    Notificacion.objects.create(
        usuario=entregable.junior_asignado, entregable=entregable, tipo=Notificacion.Tipo.ASIGNACION,
        mensaje=texto_asignacion(entregable),
    )
