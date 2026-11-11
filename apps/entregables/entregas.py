"""Entregas al cliente y actas de conformidad (SDD del Sprint 2, RF-29 y §7.4). Las reglas viven aquí, no en las vistas.

    Aprobado ──registrar──→ Entregado (entrega n.º 1, acta PENDIENTE) ──registrar_acta──→ RECIBIDA | OBSERVADA
                                  ↑                                                              │
                                  └──── nueva entrega n.º 2 ←── reabrir (servicios.mover) ←──────┘ (solo OBSERVADA)

- `registrar` es el único camino para pasar a Entregado desde la interfaz: en UNA transacción valida la fecha (no futura) y el
  medio, crea el adjunto del cargo (con `validar_archivo`, bloqueado), crea la `Entrega` con el número siguiente y el acta
  PENDIENTE y llama a `servicios.mover(..., HECHO)`, que exige y consume esa entrega y bloquea la versión enviada.
- Registrar la entrega y el acta: senior del entregable, gerente y admin (como el paso a Entregado del Sprint 1).
- El acta (RECIBIDA u OBSERVADA) exige su archivo; solo se registra o actualiza la del último envío mientras el entregable
  sigue «Entregado». Cada archivo del acta es una versión nueva (nada se sobrescribe) y queda bloqueado.
- Reabrir (HECHO → EN_PROCESO) es de `servicios.mover`: no hay otro camino para cambiar de estado.
"""
import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.alertas.models import Notificacion

from . import adjuntos, servicios
from .models import Adjunto, Entrega, Entregable
from .tipos import TIPOS_DE_ENTREGA, TIPOS_GENERADOS, TipoAdjunto
from .visibilidad import entregables_visibles, es_senior_del_entregable

E = Entregable.Estado
A = Entrega.ActaEstado

COMENTARIO_MAX = 255


def puede_registrar(usuario, entregable):
    """Registrar la entrega y el acta: senior del entregable, gerente y admin (SDD del Sprint 2, §8)."""
    return es_senior_del_entregable(usuario, entregable)


def visibles(usuario):
    """Entregas de los entregables que el usuario puede ver (los filtros solo reducen este conjunto)."""
    return Entrega.objects.filter(entregable__in=entregables_visibles(usuario).values("pk"))


def versiones_enviables(entregable):
    """Versiones que se pueden indicar como la enviada: todos los adjuntos del entregable salvo el cargo y el acta."""
    return (Adjunto.objects.filter(entregable=entregable).exclude(tipo__in=TIPOS_GENERADOS)
            .order_by("tipo", "-version"))


def version_por_defecto(entregable):
    """La versión final vigente, si la hay."""
    return adjuntos.vigente(entregable, TipoAdjunto.VERSION_FINAL)


def _resolver_version(entregable, version_enviada):
    if version_enviada in (None, ""):
        version = version_por_defecto(entregable)
        if version is None:
            raise ValidationError(
                f"Falta la versión enviada: suba una «{adjuntos.etiqueta_tipo(TipoAdjunto.VERSION_FINAL)}» o elija la "
                "versión que se envía al cliente."
            )
        return version
    pk = getattr(version_enviada, "pk", version_enviada)
    try:
        return versiones_enviables(entregable).get(pk=int(pk))
    except (TypeError, ValueError, OverflowError, Adjunto.DoesNotExist):
        raise ValidationError("La versión enviada debe ser un adjunto de este mismo entregable.")


def _borrar_archivos(creados):
    """Si la transacción se revierte, los archivos ya escritos en disco no quedan huérfanos."""
    for adjunto in creados:
        nombre = adjunto.archivo.name
        if nombre:
            try:
                adjunto.archivo.storage.delete(nombre)
            except OSError:  # pragma: no cover - nada más que hacer: el error original es el que importa
                pass


# ------------------------------------------------------------------ entregar

def registrar(entregable, usuario, fecha_entrega, medio, cargo, version_enviada=None, comentario=""):
    """Registra la entrega y pasa el entregable de «Aprobado» a «Entregado», todo o nada. Devuelve la `Entrega`.

    `cargo`: archivo del cargo de recepción (obligatorio, validado con `validar_archivo`). `version_enviada`: un adjunto del
    mismo entregable (o su id); por defecto, la versión final vigente. Lanza ValidationError o PermissionDenied.
    """
    if not puede_registrar(usuario, entregable):
        raise PermissionDenied("Solo el senior del entregable, el gerente y el admin registran entregas.")
    if entregable.estado != E.LISTO_PARA_ENTREGA:
        raise ValidationError(
            f"Solo se registra la entrega de un entregable «{E.LISTO_PARA_ENTREGA.label}»; este está "
            f"«{entregable.get_estado_display()}»."
        )
    errores = []
    if not isinstance(fecha_entrega, datetime.date):
        errores.append("Falta la fecha de entrega.")
    elif fecha_entrega > timezone.localdate():
        errores.append("La fecha de entrega no puede ser futura.")
    if medio not in Entrega.Medio.values:
        errores.append("Elija el medio de entrega.")
    if cargo is None:
        errores.append("Falta el cargo de recepción. Sin él no se puede marcar como entregado.")
    comentario = (comentario or "").strip()
    if len(comentario) > COMENTARIO_MAX:
        errores.append(f"El comentario no puede superar los {COMENTARIO_MAX} caracteres.")
    if errores:
        raise ValidationError(errores)
    version = _resolver_version(entregable, version_enviada)

    creados = []
    try:
        with transaction.atomic():
            Entregable.objects.select_for_update().get(pk=entregable.pk)  # dos registros a la vez no repiten el número
            numero = (Entrega.objects.filter(entregable=entregable).aggregate(m=Max("numero"))["m"] or 0) + 1
            adjunto_cargo = adjuntos.crear_adjunto(
                entregable, usuario, cargo, TipoAdjunto.CARGO_RECEPCION, comentario, bloqueado=True,
                detalle=lambda a: (f"Registró el cargo de recepción de la entrega n.º {numero}: v{a.version} "
                                   f"({a.nombre_original}, {Entrega.Medio(medio).label}, {fecha_entrega:%d/%m/%Y})"),
            )
            creados.append(adjunto_cargo)
            entrega = Entrega.objects.create(
                entregable=entregable, numero=numero, fecha_entrega=fecha_entrega, medio=medio, cargo=adjunto_cargo,
                version_enviada=version, registrada_por=usuario,
            )
            servicios.mover(entregable, E.HECHO, usuario)  # exige y consume esta entrega; bloquea la versión enviada
    except Exception:
        _borrar_archivos(creados)
        raise
    entrega.refresh_from_db()  # `mover` la cerró (cierre) y bloqueó la versión enviada con otra instancia
    return entrega


# ------------------------------------------------------------------ acta

def texto_acta(entrega, estado):
    e = entrega.entregable
    if estado == A.OBSERVADA:
        return (f"El acta de conformidad de la entrega n.º {entrega.numero} de {e.referencia} quedó observada: el trabajo "
                "puede reabrirse para corrección.")
    return f"El acta de conformidad de la entrega n.º {entrega.numero} de {e.referencia} fue recibida."


def texto_acta_pendiente(entrega, dias):
    e = entrega.entregable
    return (f"El acta de conformidad de la entrega n.º {entrega.numero} de {e.referencia} sigue pendiente: "
            f"{dias} días desde la entrega del {entrega.fecha_entrega:%d/%m/%Y}.")


def enlace_entregas(entregable):
    """Ruta interna a la sección «Entregas y acta» del detalle (destino de los avisos de acta)."""
    from django.urls import reverse

    return reverse("entregable_detalle", args=[entregable.pk]) + "#entregas"


def registrar_acta(entrega, usuario, estado, archivo):
    """Registra o actualiza el acta de conformidad: RECIBIDA u OBSERVADA, con su archivo (obligatorio).

    Senior del entregable, gerente y admin. Solo se registra el acta de la última entrega, mientras el entregable está
    «Entregado». Cada archivo es una versión nueva del acta, bloqueada. Avisa al junior asignado y al senior revisor
    (tipo ACTA), salvo a quien la registra. Devuelve la entrega.
    """
    entregable = entrega.entregable
    if not puede_registrar(usuario, entregable):
        raise PermissionDenied("Solo el senior del entregable, el gerente y el admin registran el acta.")
    if estado not in (A.RECIBIDA, A.OBSERVADA):
        raise ValidationError(f"Elija el estado del acta: «{A.RECIBIDA.label}» u «{A.OBSERVADA.label}».")
    if archivo is None:
        raise ValidationError(f"Adjunte el archivo del acta de conformidad: es obligatorio si el acta está "
                              f"«{A.RECIBIDA.label}» u «{A.OBSERVADA.label}».")
    creados = []
    try:
        with transaction.atomic():
            Entregable.objects.select_for_update().get(pk=entregable.pk)
            entrega = Entrega.objects.get(pk=entrega.pk)
            entregable.refresh_from_db(fields=["estado"])
            ultima = servicios.ultima_entrega(entregable)
            if entregable.estado != E.HECHO or ultima is None or ultima.pk != entrega.pk:
                raise ValidationError(
                    f"El acta solo se registra para la última entrega, mientras el entregable está «{E.HECHO.label}»."
                )
            adjunto_acta = adjuntos.crear_adjunto(
                entregable, usuario, archivo, TipoAdjunto.ACTA_CONFORMIDAD, bloqueado=True,
                detalle=lambda a: (f"Registró el acta de conformidad de la entrega n.º {entrega.numero}: "
                                   f"{Entrega.ActaEstado(estado).label} (v{a.version}, {a.nombre_original})"),
            )
            creados.append(adjunto_acta)
            entrega.acta, entrega.acta_estado, entrega.acta_actualizada_en = adjunto_acta, estado, timezone.now()
            entrega.save(update_fields=["acta", "acta_estado", "acta_actualizada_en"])
            entrega.entregable = entregable
            for destinatario in dict.fromkeys([entregable.junior_asignado, entregable.senior_revisor]):
                if destinatario.pk != usuario.pk:
                    Notificacion.objects.create(
                        usuario=destinatario, entregable=entregable, tipo=Notificacion.Tipo.ACTA,
                        mensaje=texto_acta(entrega, estado)[:255], enlace=enlace_entregas(entregable),
                    )
    except Exception:
        _borrar_archivos(creados)
        raise
    return entrega
