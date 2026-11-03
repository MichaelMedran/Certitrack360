"""Filtros del historial de observaciones (SDD del Sprint 2, RF-27; HU-12 criterio 5).

Igual que en el tablero: se aplican SIEMPRE sobre las observaciones de los entregables visibles
(`observaciones.visibles`) y solo pueden reducir ese conjunto. Un valor que no es válido se ignora.
"""
from collections import namedtuple

from django.db.models import Q

from apps.clientes.models import Cliente, Contrato
from apps.cuentas.models import Usuario

from .filtros import entero
from .models import Observacion, TipoError
from .visibilidad import entregables_visibles

Resultado = namedtuple("Resultado", "queryset activos")

TEXTO_MAX = 100

TITULOS = [("cliente", "Cliente"), ("contrato", "Contrato"), ("entregable", "Entregable"), ("responsable", "Responsable"),
           ("estado", "Estado"), ("tipo_error", "Tipo de error")]


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

    texto = (params.get("entregable") or "").strip()[:TEXTO_MAX]
    if texto:
        qs = qs.filter(Q(entregable__codigo__icontains=texto) | Q(entregable__titulo__icontains=texto))
        activos["entregable"] = texto

    responsable = entero(params.get("responsable"))
    if responsable is not None:
        qs = qs.filter(responsable_id=responsable)
        activos["responsable"] = responsable

    estado = params.get("estado")
    if estado in Observacion.Estado.values:
        qs = qs.filter(estado=estado)
        activos["estado"] = estado

    tipo = params.get("tipo_error")
    if tipo in TipoError.values:
        qs = qs.filter(tipo_error=tipo)
        activos["tipo_error"] = tipo

    qs = qs.select_related(
        "entregable__contrato__cliente", "responsable", "autor"
    ).order_by("-creada_en", "-id")
    return Resultado(qs, activos)


def opciones(usuario):
    """Desplegables: solo clientes, contratos y responsables de lo que el usuario ya puede ver."""
    visibles = entregables_visibles(usuario).values("pk")
    return {
        "clientes": Cliente.objects.filter(contratos__entregables__in=visibles).distinct().order_by("nombre"),
        "contratos": Contrato.objects.filter(entregables__in=visibles).select_related("cliente").distinct()
        .order_by("numero_contrato"),
        "responsables": Usuario.objects.filter(observaciones_a_cargo__entregable__in=visibles).distinct()
        .order_by("first_name", "last_name", "username"),
        "estados": Observacion.Estado.choices,
        "tipos": TipoError.choices,
    }


def chips(params, activos, opciones_):
    nombres = {
        "cliente": {c.pk: c.nombre for c in opciones_["clientes"]},
        "contrato": {c.pk: c.numero_contrato for c in opciones_["contratos"]},
        "responsable": {u.pk: u.nombre for u in opciones_["responsables"]},
        "estado": dict(opciones_["estados"]),
        "tipo_error": dict(opciones_["tipos"]),
    }
    salida = []
    for clave, titulo in TITULOS:
        if clave in activos:
            resto = params.copy()
            resto.pop(clave, None)
            resto.pop("pagina", None)
            valor = activos[clave] if clave == "entregable" else nombres[clave].get(activos[clave], "no disponible")
            salida.append({"clave": clave, "texto": f"{titulo}: {valor}", "quitar": "?" + resto.urlencode()})
    return salida
