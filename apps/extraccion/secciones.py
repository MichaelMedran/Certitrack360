"""Sección «Extraer datos» del detalle del entregable (cuerpo, antes del historial)."""
from . import servicios


def seccion_detalle(usuario, entregable):
    if not servicios.puede_extraer(usuario, entregable) or not (entregable.plantilla.campos_requeridos or []):
        return None
    legibles = [a for a in entregable.adjuntos.order_by("-subido_en") if servicios.es_legible(a.nombre_original)]
    return {
        "orden": 55, "plantilla": "extraccion/_seccion.html",
        "contexto": {"adjuntos": legibles, "motores": servicios.estado_de_motores()},
    }
