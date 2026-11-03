"""Filtros del listado de fichas de levantamiento (SDD del Sprint 2, RF-30 y §7.5)."""
from collections import namedtuple

from apps.clientes.models import Cliente, Contrato
from apps.entregables.filtros import entero

from .models import FichaLevantamiento
from .visibilidad import fichas_visibles

Resultado = namedtuple("Resultado", "queryset activos")

ESTADOS_FILTRO = [
    *FichaLevantamiento.Estado.choices,
    *FichaLevantamiento.EstadoDocumental.choices,
]

TITULOS = [
    ("cliente", "Cliente"),
    ("contrato", "Contrato"),
    ("estado", "Estado"),
    ("estado_documental", "Estado documental"),
]


def aplicar(qs, params):
    activos = {}

    cliente = entero(params.get("cliente"))
    if cliente is not None:
        qs = qs.filter(contrato__cliente_id=cliente)
        activos["cliente"] = cliente

    contrato = entero(params.get("contrato"))
    if contrato is not None:
        qs = qs.filter(contrato_id=contrato)
        activos["contrato"] = contrato

    estado = params.get("estado")
    if estado in FichaLevantamiento.Estado.values:
        qs = qs.filter(estado=estado)
        activos["estado"] = estado
    elif estado in FichaLevantamiento.EstadoDocumental.values:
        qs = qs.filter(estado_documental=estado)
        activos["estado"] = estado

    estado_doc = params.get("estado_documental")
    if estado_doc in FichaLevantamiento.EstadoDocumental.values:
        qs = qs.filter(estado_documental=estado_doc)
        activos["estado_documental"] = estado_doc

    qs = qs.select_related("contrato__cliente", "responsable", "confirmada_por").order_by("-actualizada_en", "-id")
    return Resultado(qs, activos)


def opciones(usuario):
    """Desplegables: solo clientes y contratos de las fichas que el usuario puede ver."""
    visibles = fichas_visibles(usuario).values("pk")
    return {
        "clientes": Cliente.objects.filter(contratos__fichas__in=visibles).distinct().order_by("nombre"),
        "contratos": (
            Contrato.objects.filter(fichas__in=visibles)
            .select_related("cliente")
            .distinct()
            .order_by("numero_contrato")
        ),
        "estados": ESTADOS_FILTRO,
    }


def chips(params, activos, opciones_):
    nombres = {
        "cliente": {c.pk: c.nombre for c in opciones_["clientes"]},
        "contrato": {c.pk: c.numero_contrato for c in opciones_["contratos"]},
        "estado": dict(ESTADOS_FILTRO),
        "estado_documental": dict(FichaLevantamiento.EstadoDocumental.choices),
    }
    salida = []
    for clave, titulo in TITULOS:
        if clave in activos:
            resto = params.copy()
            resto.pop(clave, None)
            valor = nombres[clave].get(activos[clave], "no disponible")
            salida.append({"clave": clave, "texto": f"{titulo}: {valor}", "quitar": "?" + resto.urlencode()})
    return salida
