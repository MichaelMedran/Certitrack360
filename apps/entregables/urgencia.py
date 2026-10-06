"""Urgencia de un entregable: se calcula en el momento y no se almacena (SDD §10.3, RF-15).

Los umbrales salen de la misma configuración que las alertas (`ALERT_THRESHOLDS_DAYS`, por defecto 5,2,0):
  - CRITICO: vence en `critico` días o menos (el menor umbral positivo; 2 por defecto).
  - PROXIMO: vence en `proximo` días o menos (el mayor umbral; 5 por defecto).
  - VENCIDO: el plazo ya pasó y el entregable no está en HECHO.
  - NORMAL: el resto. Un entregable HECHO ya no corre contra el plazo, así que siempre es NORMAL.
"""
import datetime

from django.conf import settings
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone

from .models import Entregable

VENCIDO, CRITICO, PROXIMO, NORMAL = "VENCIDO", "CRITICO", "PROXIMO", "NORMAL"
ETIQUETAS = {VENCIDO: "Vencido", CRITICO: "Crítico", PROXIMO: "Próximo", NORMAL: "Normal"}
CHOICES = list(ETIQUETAS.items())


def umbrales():
    """(días de «crítico», días de «próximo»), leídos de la configuración en cada llamada."""
    todos = sorted(set(settings.ALERT_THRESHOLDS_DAYS))
    positivos = [u for u in todos if u > 0]
    return (min(positivos) if positivos else 0), (max(todos) if todos else 0)


def calcular(plazo, estado, hoy=None):
    hoy = hoy or timezone.localdate()
    if estado == Entregable.Estado.HECHO:
        return NORMAL
    dias = (plazo - hoy).days
    critico, proximo = umbrales()
    if dias < 0:
        return VENCIDO
    if dias <= critico:
        return CRITICO
    if dias <= proximo:
        return PROXIMO
    return NORMAL


def condicion(urgencia, hoy=None):
    """Condición de base de datos equivalente a `calcular(...) == urgencia`."""
    hoy = hoy or timezone.localdate()
    critico, proximo = umbrales()
    limite_critico = hoy + datetime.timedelta(days=critico)
    limite_proximo = hoy + datetime.timedelta(days=proximo)
    activo = ~Q(estado=Entregable.Estado.HECHO)
    if urgencia == VENCIDO:
        return activo & Q(plazo__lt=hoy)
    if urgencia == CRITICO:
        return activo & Q(plazo__gte=hoy, plazo__lte=limite_critico)
    if urgencia == PROXIMO:
        return activo & Q(plazo__gt=limite_critico, plazo__lte=limite_proximo)
    if urgencia == NORMAL:
        return Q(estado=Entregable.Estado.HECHO) | Q(plazo__gt=limite_proximo)
    raise ValueError(f"Urgencia desconocida: {urgencia}")


def rango(hoy=None):
    """Expresión para ordenar: vencidos primero, luego críticos, próximos y normales; los HECHO al final."""
    hoy = hoy or timezone.localdate()
    critico, proximo = umbrales()
    return Case(
        When(estado=Entregable.Estado.HECHO, then=Value(4)),
        When(plazo__lt=hoy, then=Value(0)),
        When(plazo__lte=hoy + datetime.timedelta(days=critico), then=Value(1)),
        When(plazo__lte=hoy + datetime.timedelta(days=proximo), then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )
