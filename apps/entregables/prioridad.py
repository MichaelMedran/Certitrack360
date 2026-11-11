"""Prioridad de un entregable (SDD del Sprint 3, §7.3, RF-42, HU-29).

Se calcula en el momento y no se guarda: por eso cambia sola al cambiar el plazo, el tipo de cliente o una alerta urgente
(criterio 4 de HU-29). Combina la urgencia del Sprint 1 (`urgencia.py`, que no cambia), el tipo de cliente y la alerta de
urgencia fuera de horario (RF-43):

  - ALTA:  vencido, crítico, con alerta urgente abierta, o próximo y de cliente Estratégico.
  - MEDIA: próximo (no estratégico), o normal de cliente Estratégico que vence en `PRIORIDAD_DIAS_ESTRATEGICO` días o menos.
  - BAJA:  el resto. Un entregable Entregado no tiene prioridad (None).

Orden «prioridad»: nivel, alerta urgente abierta primero, plazo más próximo, tipo de cliente (Estratégico, Regular,
Ocasional) e id.

Alerta urgente (S3-H4, app `urgencias`): este módulo espera el modelo `urgencias.AlertaUrgente` con los campos `entregable`
(FK) y `cerrada_en` (nulo mientras la alerta está abierta). Si el modelo todavía no existe (o no tiene esos campos), se
trata como «sin alertas» y la prioridad se calcula solo con plazo y tipo de cliente.
"""
import datetime

from django.apps import apps
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.db.models import BooleanField, Case, Exists, IntegerField, OuterRef, Q, Value, When
from django.utils import timezone

from apps.clientes.models import Cliente

from . import urgencia as urg
from .models import Entregable

ALTA, MEDIA, BAJA = "ALTA", "MEDIA", "BAJA"
ETIQUETAS = {ALTA: "Alta", MEDIA: "Media", BAJA: "Baja"}
CHOICES = list(ETIQUETAS.items())

_RANGO_NIVEL = {ALTA: 0, MEDIA: 1, BAJA: 2}
_RANGO_TIPO = {Cliente.Tipo.ESTRATEGICO: 0, Cliente.Tipo.REGULAR: 1, Cliente.Tipo.OCASIONAL: 2}
_SIN_PRIORIDAD = 3  # los Entregados van al final


def dias_estrategico():
    return int(getattr(settings, "PRIORIDAD_DIAS_ESTRATEGICO", 10))


# ------------------------------------------------------------------ alertas urgentes (acceso defensivo)

def _modelo_alerta():
    """`urgencias.AlertaUrgente` si existe y tiene `entregable` y `cerrada_en`; si no, None."""
    try:
        modelo = apps.get_model("urgencias", "AlertaUrgente")
        modelo._meta.get_field("entregable")
        modelo._meta.get_field("cerrada_en")
    except (LookupError, FieldDoesNotExist):
        return None
    return modelo


def _alerta_abierta():
    """Expresión de base de datos: ¿el entregable tiene una alerta urgente sin cerrar?"""
    modelo = _modelo_alerta()
    if modelo is None:
        return Value(False, output_field=BooleanField())
    return Exists(modelo._default_manager.filter(entregable_id=OuterRef("pk"), cerrada_en__isnull=True))


def con_alerta_abierta(ids):
    """Conjunto de ids (de `ids`) que tienen una alerta urgente abierta; una sola consulta."""
    modelo = _modelo_alerta()
    ids = list(ids)
    if modelo is None or not ids:
        return set()
    return set(
        modelo._default_manager.filter(entregable_id__in=ids, cerrada_en__isnull=True).values_list("entregable_id", flat=True)
    )


# ------------------------------------------------------------------ cálculo de un entregable

def calcular(plazo, estado, tipo_cliente, alerta_abierta=False, hoy=None):
    """ALTA, MEDIA o BAJA; None si el entregable ya está Entregado."""
    hoy = hoy or timezone.localdate()
    if estado == Entregable.Estado.HECHO:
        return None
    nivel = urg.calcular(plazo, estado, hoy)
    estrategico = tipo_cliente == Cliente.Tipo.ESTRATEGICO
    if alerta_abierta or nivel in (urg.VENCIDO, urg.CRITICO) or (nivel == urg.PROXIMO and estrategico):
        return ALTA
    if nivel == urg.PROXIMO or (estrategico and (plazo - hoy).days <= dias_estrategico()):
        return MEDIA
    return BAJA


def enriquecer(entregables, hoy=None):
    """Pone `prioridad` (ALTA/MEDIA/BAJA o None), `prioridad_etiqueta` y `alerta_urgente` en cada entregable.

    Usa una sola consulta para las alertas. Los entregables deben traer `contrato__cliente` (select_related).
    """
    hoy = hoy or timezone.localdate()
    entregables = list(entregables)
    con_alerta = con_alerta_abierta(e.pk for e in entregables if e.estado != Entregable.Estado.HECHO)
    for e in entregables:
        e.alerta_urgente = e.pk in con_alerta
        e.prioridad = calcular(e.plazo, e.estado, e.contrato.cliente.tipo, e.alerta_urgente, hoy)
        e.prioridad_etiqueta = ETIQUETAS.get(e.prioridad, "")
    return entregables


def enriquecer_tarjetas(entregables, usuario=None):
    """Punto de extensión `registrar_tarjeta`: la insignia de prioridad del tablero y de la lista."""
    enriquecer(entregables)


# ------------------------------------------------------------------ consultas

def condicion(nivel, hoy=None):
    """Condición de base de datos equivalente a `calcular(...) == nivel`. Requiere la anotación de `anotar`."""
    hoy = hoy or timezone.localdate()
    activo = ~Q(estado=Entregable.Estado.HECHO)
    estrategico = Q(contrato__cliente__tipo=Cliente.Tipo.ESTRATEGICO)
    alta = (
        urg.condicion(urg.VENCIDO, hoy) | urg.condicion(urg.CRITICO, hoy) | Q(tiene_alerta_urgente=True)
        | (urg.condicion(urg.PROXIMO, hoy) & estrategico)
    )
    media = urg.condicion(urg.PROXIMO, hoy) | (
        estrategico & Q(plazo__lte=hoy + datetime.timedelta(days=dias_estrategico()))
    )
    if nivel == ALTA:
        return activo & alta
    if nivel == MEDIA:
        return activo & media & ~alta
    if nivel == BAJA:
        return activo & ~alta & ~media
    raise ValueError(f"Prioridad desconocida: {nivel}")


def anotar(qs, hoy=None):
    """Agrega `tiene_alerta_urgente`, `rango_prioridad` (0 Alta, 1 Media, 2 Baja, 3 Entregado) y `rango_tipo_cliente`."""
    if "rango_prioridad" in qs.query.annotations:  # ya anotado (p. ej. por el filtro): no repetir
        return qs
    hoy = hoy or timezone.localdate()
    qs = qs.annotate(tiene_alerta_urgente=_alerta_abierta())
    return qs.annotate(
        rango_prioridad=Case(
            When(estado=Entregable.Estado.HECHO, then=Value(_SIN_PRIORIDAD)),
            When(condicion(ALTA, hoy), then=Value(_RANGO_NIVEL[ALTA])),
            When(condicion(MEDIA, hoy), then=Value(_RANGO_NIVEL[MEDIA])),
            default=Value(_RANGO_NIVEL[BAJA]),
            output_field=IntegerField(),
        ),
        rango_alerta=Case(When(tiene_alerta_urgente=True, then=Value(0)), default=Value(1), output_field=IntegerField()),
        rango_tipo_cliente=Case(
            *[When(contrato__cliente__tipo=tipo, then=Value(rango)) for tipo, rango in _RANGO_TIPO.items()],
            default=Value(len(_RANGO_TIPO)),
            output_field=IntegerField(),
        ),
    )


def ordenar(qs, hoy=None):
    """Orden por defecto: nivel, alerta abierta primero, plazo más próximo, tipo de cliente e id."""
    return anotar(qs, hoy).order_by("rango_prioridad", "rango_alerta", "plazo", "rango_tipo_cliente", "id")


def filtrar(qs, nivel, hoy=None):
    """Solo los entregables con la prioridad pedida (sin ampliar el queryset recibido)."""
    return anotar(qs, hoy).filter(condicion(nivel, hoy))
