"""Vista del buscador global `/buscar/` con actualización parcial por HTMX (SDD del Sprint 2, RF-36: HU-21)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.entregables.htmx import con_vary, pide_parcial

from .servicios import buscar, chips_filtros


@login_required
def vista_buscar(request):
    datos = buscar(request.user, request.GET)
    chips = chips_filtros(request.GET, datos["filtros_activos"], datos["opciones"])
    contexto = {
        **datos,
        "chips": chips,
    }
    if pide_parcial(request):
        return con_vary(render(request, "busqueda/_resultados.html", {**contexto, "es_htmx": True}))
    return con_vary(render(request, "busqueda/buscar.html", contexto))
