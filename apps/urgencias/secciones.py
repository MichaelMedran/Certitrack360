"""Sección «Alerta urgente» del detalle del entregable (zona de cuerpo)."""
from apps.entregables.models import Entregable

from . import servicios
from .forms import ActivarAlertaForm


def seccion_detalle(usuario, entregable):
    alerta = servicios.abierta_de(entregable)
    ultima_cerrada = None
    if alerta is None:
        ultima_cerrada = entregable.alertas_urgentes.select_related("aceptada_por", "activada_por").first()
    puede_activar = (
        alerta is None and entregable.estado != Entregable.Estado.HECHO and servicios.puede_activar(usuario, entregable)
    )
    if alerta is None and ultima_cerrada is None and not puede_activar:
        return None  # nada que mostrar (p. ej. a un junior sin alertas)
    contexto = {
        "alerta": alerta, "ultima_cerrada": ultima_cerrada, "puede_activar": puede_activar,
        "form": ActivarAlertaForm(auto_id="urg_%s") if puede_activar else None,
    }
    if alerta is not None:
        contexto.update(servicios.resumen(alerta))
        contexto["ya_leyo"] = alerta.lecturas.filter(usuario=usuario).exists()
        contexto["puede_responder"] = servicios.puede_responder(usuario, alerta)
    return {"orden": 5, "zona": "cuerpo", "plantilla": "urgencias/_seccion.html", "contexto": contexto}
