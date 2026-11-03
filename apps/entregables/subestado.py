"""Subestado calculado «Con correcciones pendientes» (SDD del Sprint 2, RF-26, C3 y §7.1).

No es una sexta columna ni se guarda: aplica cuando el entregable está «En proceso» (EN_PROCESO) y tiene observaciones
abiertas (PENDIENTE o EN_CORRECCION). Se muestra como texto en la tarjeta, la lista, el detalle y el calendario, y es una
opción más del filtro de estado. Se calcula con EXISTS en la misma consulta del listado (sin una consulta por fila).
"""
from django.db.models import Exists, OuterRef, Q

from .models import Entregable, Observacion

VALOR = "CON_CORRECCIONES"  # valor del filtro de estado (no es un código de estado: no se guarda)
ETIQUETA = "Con correcciones pendientes"


def hay_abiertas():
    """Expresión EXISTS: el entregable de la fila tiene observaciones abiertas."""
    return Exists(Observacion.objects.abiertas().filter(entregable=OuterRef("pk")))


def condicion():
    """Q del subestado, para filtrar un queryset de entregables (solo puede reducirlo)."""
    return Q(estado=Entregable.Estado.EN_PROCESO) & Q(hay_abiertas())


def anotar(qs):
    """Agrega `obs_abiertas` (bool) a cada entregable del queryset."""
    return qs.annotate(obs_abiertas=hay_abiertas())


def aplica(entregable, hay_observaciones_abiertas=None):
    """True si el entregable está En proceso con observaciones abiertas. Usa la anotación si existe (sin consultas)."""
    if entregable.estado != Entregable.Estado.EN_PROCESO:
        return False
    if hay_observaciones_abiertas is None:
        hay_observaciones_abiertas = getattr(entregable, "obs_abiertas", None)
    if hay_observaciones_abiertas is None:
        hay_observaciones_abiertas = entregable.observaciones.abiertas().exists()
    return bool(hay_observaciones_abiertas)


def estados_con_subestado():
    """Opciones del filtro de estado: los cinco estados y, después de «En proceso», el subestado."""
    opciones = []
    for valor, etiqueta in Entregable.Estado.choices:
        opciones.append((valor, etiqueta))
        if valor == Entregable.Estado.EN_PROCESO:
            opciones.append((VALOR, ETIQUETA))
    return opciones
