"""Sección «Etiquetas» del detalle del entregable (zona de cabecera)."""
from . import servicios
from .models import Etiqueta


def seccion_detalle(usuario, entregable):
    puede_asignar = servicios.puede_asignar(usuario, entregable)
    propias = set(Etiqueta.objects.filter(entregables=entregable).values_list("pk", flat=True))
    return {
        "orden": 10, "zona": "cabecera", "plantilla": "etiquetas/_seccion.html",
        "contexto": {
            "etiquetas": servicios.etiquetas_de(entregable),
            "puede_asignar": puede_asignar,
            "puede_crear": servicios.puede_crear(usuario),
            "ofrecidas": list(servicios.ofrecidas_para(entregable)) if puede_asignar else [],
            "propias": propias,
            "colores": Etiqueta.Color.choices,
        },
    }
