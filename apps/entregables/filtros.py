"""Filtros y orden de entregables para el tablero y la lista (SDD RF-15).

Regla de seguridad: los filtros se aplican SIEMPRE sobre un queryset que ya viene restringido por rol
(`entregables_visibles`) y solo pueden reducirlo, nunca ampliarlo. Un valor que no corresponde a algo
visible simplemente no devuelve nada.
"""
from collections import namedtuple

from django.db.models import Q
from django.utils import timezone

from apps.clientes.models import Cliente, Contrato
from apps.cuentas.models import Usuario

from . import urgencia as urg
from .models import Entregable, Observacion, TipoError
from .visibilidad import entregables_visibles

ORDEN_CHOICES = [("plazo", "Plazo (más próximo primero)"), ("urgencia", "Urgencia"), ("cliente", "Cliente")]
ORDENES = [valor for valor, _ in ORDEN_CHOICES]

Resultado = namedtuple("Resultado", "queryset activos orden")


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def aplicar(qs, params, hoy=None):
    """Aplica los filtros de `params` (p. ej. request.GET) y el orden. Los valores no válidos se ignoran.

    Devuelve un `Resultado(queryset, activos, orden)`; `activos` tiene solo los filtros realmente aplicados.
    """
    hoy = hoy or timezone.localdate()
    activos = {}

    cliente = _entero(params.get("cliente"))
    if cliente is not None:
        qs = qs.filter(contrato__cliente_id=cliente)
        activos["cliente"] = cliente

    contrato = _entero(params.get("contrato"))
    if contrato is not None:
        qs = qs.filter(contrato_id=contrato)
        activos["contrato"] = contrato

    responsable = _entero(params.get("responsable"))
    if responsable is not None:
        qs = qs.filter(Q(junior_asignado_id=responsable) | Q(senior_revisor_id=responsable))
        activos["responsable"] = responsable

    estado = params.get("estado")
    if estado in Entregable.Estado.values:
        qs = qs.filter(estado=estado)
        activos["estado"] = estado

    urgencia = params.get("urgencia")
    if urgencia in urg.ETIQUETAS:
        qs = qs.filter(urg.condicion(urgencia, hoy))
        activos["urgencia"] = urgencia

    tipo = params.get("tipo_observacion")
    if tipo in TipoError.values:
        # Solo observaciones abiertas (no resueltas) del tipo pedido.
        abiertas = Observacion.objects.filter(tipo_error=tipo, resuelta=False).values("entregable_id")
        qs = qs.filter(pk__in=abiertas)
        activos["tipo_observacion"] = tipo

    orden = params.get("orden")
    if orden not in ORDENES:
        orden = "plazo"
    return Resultado(ordenar(qs, orden, hoy), activos, orden)


def ordenar(qs, orden, hoy=None):
    if orden == "urgencia":
        return qs.annotate(rango_urgencia=urg.rango(hoy)).order_by("rango_urgencia", "plazo", "id")
    if orden == "cliente":
        return qs.order_by("contrato__cliente__nombre", "plazo", "id")
    return qs.order_by("plazo", "id")


def opciones(usuario):
    """Contenido de los desplegables: solo clientes, contratos y personas de lo que el usuario ya puede ver."""
    visibles = entregables_visibles(usuario).values("pk")
    return {
        "clientes": Cliente.objects.filter(contratos__entregables__in=visibles).distinct(),
        "contratos": Contrato.objects.filter(entregables__in=visibles).select_related("cliente").distinct(),
        "responsables": Usuario.objects.filter(
            Q(entregables_asignados__in=visibles) | Q(entregables_a_revisar__in=visibles)
        ).distinct().order_by("first_name", "last_name", "username"),
        "estados": Entregable.Estado.choices,
        "urgencias": urg.CHOICES,
        "tipos_observacion": TipoError.choices,
        "ordenes": ORDEN_CHOICES,
    }
