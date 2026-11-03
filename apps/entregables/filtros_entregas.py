"""Filtros del historial de entregas (SDD del Sprint 2, RF-29 y §7.4; HU-19 criterio 5).

Igual que el tablero y el historial de observaciones: se aplican SIEMPRE sobre las entregas de los entregables visibles
(`entregas.visibles`) y solo pueden reducir ese conjunto. Un valor que no es válido se ignora. El periodo es por la fecha
de entrega (desde y hasta, inclusive).
"""
import datetime
from collections import namedtuple

from apps.clientes.models import Cliente, Contrato

from .filtros import entero
from .models import Entrega
from .visibilidad import entregables_visibles

Resultado = namedtuple("Resultado", "queryset activos")

TITULOS = [("cliente", "Cliente"), ("contrato", "Contrato"), ("desde", "Desde"), ("hasta", "Hasta"),
           ("acta", "Estado del acta")]


def fecha(valor):
    """La fecha AAAA-MM-DD de un parámetro, o None si no es una fecha válida."""
    try:
        return datetime.date.fromisoformat((valor or "").strip())
    except ValueError:
        return None


def aplicar(qs, params):
    activos = {}

    cliente = entero(params.get("cliente"))
    if cliente is not None:
        qs = qs.filter(entregable__contrato__cliente_id=cliente)
        activos["cliente"] = cliente

    contrato = entero(params.get("contrato"))
    if contrato is not None:
        qs = qs.filter(entregable__contrato_id=contrato)
        activos["contrato"] = contrato

    desde = fecha(params.get("desde"))
    if desde is not None:
        qs = qs.filter(fecha_entrega__gte=desde)
        activos["desde"] = desde

    hasta = fecha(params.get("hasta"))
    if hasta is not None:
        qs = qs.filter(fecha_entrega__lte=hasta)
        activos["hasta"] = hasta

    acta = params.get("acta")
    if acta in Entrega.ActaEstado.values:
        qs = qs.filter(acta_estado=acta)
        activos["acta"] = acta

    qs = qs.select_related(
        "entregable__contrato__cliente", "registrada_por", "cargo", "acta"
    ).order_by("-fecha_entrega", "-registrada_en", "-id")
    return Resultado(qs, activos)


def opciones(usuario):
    """Desplegables: solo clientes y contratos de lo que el usuario ya puede ver."""
    visibles = entregables_visibles(usuario).values("pk")
    return {
        "clientes": Cliente.objects.filter(contratos__entregables__in=visibles).distinct().order_by("nombre"),
        "contratos": Contrato.objects.filter(entregables__in=visibles).select_related("cliente").distinct()
        .order_by("numero_contrato"),
        "actas": Entrega.ActaEstado.choices,
    }


def chips(params, activos, opciones_):
    nombres = {
        "cliente": {c.pk: c.nombre for c in opciones_["clientes"]},
        "contrato": {c.pk: c.numero_contrato for c in opciones_["contratos"]},
        "acta": dict(opciones_["actas"]),
    }
    salida = []
    for clave, titulo in TITULOS:
        if clave in activos:
            resto = params.copy()
            resto.pop(clave, None)
            resto.pop("pagina", None)
            if clave in ("desde", "hasta"):
                valor = activos[clave].strftime("%d/%m/%Y")
            else:
                valor = nombres[clave].get(activos[clave], "no disponible")
            salida.append({"clave": clave, "texto": f"{titulo}: {valor}", "quitar": "?" + resto.urlencode()})
    return salida
