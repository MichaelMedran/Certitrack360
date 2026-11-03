import datetime
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse

from apps.entregables import filtros, urgencia
from apps.entregables.models import Entregable
from apps.entregables.visibilidad import entregables_visibles

# El color refuerza la urgencia, pero nunca es la única señal: el título lleva el estado y la urgencia en texto.
COLORES = {
    urgencia.VENCIDO: "#991b1b",
    urgencia.CRITICO: "#c2410c",
    urgencia.PROXIMO: "#a16207",
    urgencia.NORMAL: "#1e4e8c",
}
COLOR_HECHO = "#4b5563"

# Filtros del calendario (SDD del Sprint 2, RF-21; HU-02 criterio 3). La fecha se elige navegando por mes o semana.
FILTROS = ("cliente", "estado", "responsable")


def _fecha(valor):
    """Los 10 primeros caracteres de `valor` como fecha (AAAA-MM-DD), o None si no lo son."""
    try:
        return datetime.date.fromisoformat((valor or "")[:10])
    except ValueError:
        return None


def _filtros_de(params):
    """Solo los filtros del calendario; se aplican con el mismo módulo que el tablero y la lista."""
    return {clave: params[clave] for clave in FILTROS if params.get(clave)}


def titulo_evento(e, nivel):
    """Texto de cada evento (HU-02 criterio 2): estado, código, cliente, responsable (el junior asignado) y entregable.

    «[Estado] CÓDIGO Cliente (a cargo de Responsable): Título — Urgencia». La urgencia va al final y solo si no es normal,
    para que se lea en texto y no solo por el color.
    """
    titulo = (f"[{e.get_estado_display()}] {e.codigo} {e.contrato.cliente.nombre} "
              f"(a cargo de {e.junior_asignado.nombre}): {e.titulo}")
    if nivel != urgencia.NORMAL:
        titulo += f" — {urgencia.ETIQUETAS[nivel]}"
    return titulo


@login_required
def pagina(request):
    """Calendario de plazos con su panel de filtros. Las opciones salen de lo que el usuario ya puede ver."""
    resultado = filtros.aplicar(entregables_visibles(request.user), _filtros_de(request.GET))
    activos = resultado.activos
    return render(request, "calendario/calendario.html", {
        "opciones": filtros.opciones(request.user), "filtros_activos": activos, "n_filtros": len(activos),
        # Los mismos filtros viajan a la API de eventos (y FullCalendar suma el rango que muestra).
        "consulta": f"?{urlencode(activos)}" if activos else "",
    })


@login_required
def eventos(request):
    """Eventos JSON. Parte del mismo queryset de visibilidad que el resto de vistas: los filtros solo pueden reducirlo."""
    qs = entregables_visibles(request.user).select_related("contrato__cliente", "junior_asignado")
    qs = filtros.aplicar(qs, _filtros_de(request.GET)).queryset
    # Rango que pide FullCalendar (fecha ISO, a veces con hora). Una fecha no válida se ignora en lugar de dar un error 500.
    inicio, fin = _fecha(request.GET.get("start")), _fecha(request.GET.get("end"))
    if inicio:
        qs = qs.filter(plazo__gte=inicio)
    if fin:
        qs = qs.filter(plazo__lte=fin)
    datos = []
    for e in qs:
        nivel = e.urgencia
        datos.append({
            "id": e.pk,
            "title": titulo_evento(e, nivel),
            "start": e.plazo.isoformat(),
            "allDay": True,
            "url": reverse("entregable_detalle", args=[e.pk]),
            "color": COLOR_HECHO if e.estado == Entregable.Estado.HECHO else COLORES[nivel],
            "extendedProps": {"estado": e.estado, "urgencia": nivel},
        })
    return JsonResponse(datos, safe=False)
