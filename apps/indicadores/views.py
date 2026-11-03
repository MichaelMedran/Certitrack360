"""Vista del panel de indicadores de desempeño (SDD del Sprint 2, RF-33: HU-13)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .servicios import calcular_indicadores, chips_filtros


@login_required
def indicadores(request):
    datos = calcular_indicadores(request.user, request.GET)
    chips = chips_filtros(request.GET, datos["filtros_activos"], datos["opciones"])
    return render(
        request,
        "indicadores/indicadores.html",
        {
            **datos,
            "chips": chips,
        },
    )
