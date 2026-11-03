"""Filtros del historial de tiempos por etapa (SDD del Sprint 2, RF-32, §7.7 y §9.2 `s2-historiales.html`).

Se aplican siempre sobre `tiempos.visibles(usuario)` y nunca amplían la visibilidad:
- Junior: solo sus propios registros.
- Senior: los de sus entregables visibles.
- Gerente y Admin: todos.
"""
import datetime
from collections import namedtuple

from apps.clientes.models import Cliente
from apps.cuentas.models import Usuario

from .filtros import entero
from .models import RegistroTiempo
from .tiempos import formatear_segundos, visibles
from .visibilidad import entregables_visibles

Resultado = namedtuple("Resultado", "queryset activos total_segundos total_texto")

TITULOS = [
    ("cliente", "Cliente"),
    ("etapa", "Etapa"),
    ("responsable", "Responsable"),
    ("desde", "Desde"),
    ("hasta", "Hasta"),
]


def fecha(valor):
    """La fecha AAAA-MM-DD de un parámetro, o None si no es válida."""
    try:
        return datetime.date.fromisoformat((valor or "").strip())
    except ValueError:
        return None


def aplicar(qs, params, ahora=None):
    activos = {}

    cliente = entero(params.get("cliente"))
    if cliente is not None:
        qs = qs.filter(entregable__contrato__cliente_id=cliente)
        activos["cliente"] = cliente

    etapa = (params.get("etapa") or "").strip()
    if etapa in RegistroTiempo.Etapa.values:
        qs = qs.filter(etapa=etapa)
        activos["etapa"] = etapa

    responsable = entero(params.get("responsable") or params.get("usuario"))
    if responsable is not None:
        qs = qs.filter(usuario_id=responsable)
        activos["responsable"] = responsable

    desde = fecha(params.get("desde"))
    if desde is not None:
        qs = qs.filter(inicio__date__gte=desde)
        activos["desde"] = desde

    hasta = fecha(params.get("hasta"))
    if hasta is not None:
        qs = qs.filter(inicio__date__lte=hasta)
        activos["hasta"] = hasta

    qs = qs.select_related("entregable__contrato__cliente", "usuario").order_by("-inicio", "-id")
    total_seg = sum(r.segundos(ahora=ahora) for r in qs)
    return Resultado(qs, activos, total_seg, formatear_segundos(total_seg))


def opciones(usuario):
    """Desplegables: solo clientes y responsables presentes en lo que el usuario puede ver."""
    ent_visibles = entregables_visibles(usuario).values("pk")
    reg_visibles = visibles(usuario)
    if usuario.es_junior:
        responsables = Usuario.objects.filter(pk=usuario.pk)
    else:
        responsables = (
            Usuario.objects.filter(registros_tiempo__in=reg_visibles)
            .distinct()
            .order_by("first_name", "last_name", "username")
        )
    return {
        "clientes": Cliente.objects.filter(contratos__entregables__in=ent_visibles).distinct().order_by("nombre"),
        "etapas": RegistroTiempo.Etapa.choices,
        "responsables": responsables,
    }


def chips(params, activos, opciones_):
    nombres = {
        "cliente": {c.pk: c.nombre for c in opciones_["clientes"]},
        "etapa": dict(opciones_["etapas"]),
        "responsable": {u.pk: u.nombre for u in opciones_["responsables"]},
    }
    salida = []
    for clave, titulo in TITULOS:
        if clave in activos:
            resto = params.copy()
            resto.pop(clave, None)
            if clave == "responsable":
                resto.pop("usuario", None)
            resto.pop("pagina", None)
            if clave in ("desde", "hasta"):
                valor = activos[clave].strftime("%d/%m/%Y")
            else:
                valor = nombres[clave].get(activos[clave], "no disponible")
            salida.append({"clave": clave, "texto": f"{titulo}: {valor}", "quitar": "?" + resto.urlencode()})
    return salida
