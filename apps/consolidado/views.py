from django.shortcuts import render

from apps.cuentas.permisos import solo_gestion
from apps.clientes.models import Cliente
from apps.entregables import filtros
from apps.entregables.models import Entregable

from .graficos import armar_graficos
from .servicios import datos_consolidado, datos_graficos


@solo_gestion  # sin sesión: al ingreso; junior y senior: 403. Además el servicio vuelve a comprobarlo.
def consolidado(request):
    datos = datos_consolidado(request.user, request.GET)

    estados = list(Entregable.Estado.values)
    for fila in datos["por_cliente"] + datos["por_contrato"]:
        fila["celdas"] = [fila["por_estado"][estado] for estado in estados]
    for personas in (datos["carga_juniors"], datos["carga_seniors"]):
        tope = max((p["activos"] for p in personas), default=0) or 1
        for p in personas:
            p["porcentaje"] = round(100 * p["activos"] / tope)

    graficos = datos_graficos(request.user, request.GET)  # RF-49: SVG dibujado aquí, sin JavaScript

    return render(request, "consolidado/consolidado.html", {
        **datos, "opciones": filtros.opciones(request.user), "estados": Entregable.Estado.choices,
        "sectores": Cliente.Sector.choices, "graficos": armar_graficos(graficos), "texto_filtro": graficos["texto_filtro"],
        "etiqueta_cerrado": Entregable.Estado.HECHO.label,
    })
