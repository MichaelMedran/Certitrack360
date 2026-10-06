from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse

from apps.entregables import urgencia
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


@login_required
def pagina(request):
    return render(request, "calendario/calendario.html")


@login_required
def eventos(request):
    """Eventos JSON; usa el mismo queryset de visibilidad que el resto de vistas."""
    qs = entregables_visibles(request.user).select_related("contrato__cliente")
    inicio, fin = request.GET.get("start", "")[:10], request.GET.get("end", "")[:10]
    if inicio:
        qs = qs.filter(plazo__gte=inicio)
    if fin:
        qs = qs.filter(plazo__lte=fin)
    datos = []
    for e in qs:
        nivel = e.urgencia
        titulo = f"[{e.get_estado_display()}] {e.contrato.cliente.nombre}: {e.titulo}"
        if nivel != urgencia.NORMAL:
            titulo += f" — {urgencia.ETIQUETAS[nivel]}"
        datos.append({
            "id": e.pk,
            "title": titulo,
            "start": e.plazo.isoformat(),
            "allDay": True,
            "url": reverse("entregable_detalle", args=[e.pk]),
            "color": COLOR_HECHO if e.estado == Entregable.Estado.HECHO else COLORES[nivel],
            "extendedProps": {"estado": e.estado, "urgencia": nivel},
        })
    return JsonResponse(datos, safe=False)
