from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse

from apps.entregables.models import Entregable
from apps.entregables.visibilidad import entregables_visibles

COLORES = {
    Entregable.Estado.A_REALIZAR: "#64748b",
    Entregable.Estado.EN_PROCESO: "#2563eb",
    Entregable.Estado.VERIFICACION_SENIOR: "#b45309",
    Entregable.Estado.LISTO_PARA_ENTREGA: "#0f766e",
    Entregable.Estado.HECHO: "#15803d",
}


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
    datos = [
        {
            "id": e.pk,
            "title": f"{e.contrato.cliente.nombre}: {e.titulo}",
            "start": e.plazo.isoformat(),
            "allDay": True,
            "url": reverse("entregable_detalle", args=[e.pk]),
            "color": COLORES[e.estado],
        }
        for e in qs
    ]
    return JsonResponse(datos, safe=False)
