import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.entregables.models import Entregable
from apps.entregables.visibilidad import entregables_visibles


@login_required
def inicio(request):
    """Resumen según el rol del usuario."""
    hoy = timezone.localdate()
    qs = entregables_visibles(request.user).select_related("contrato__cliente", "junior_asignado")
    activos = qs.exclude(estado=Entregable.Estado.HECHO)
    contexto = {
        "total_activos": activos.count(),
        "vencidos": activos.filter(plazo__lt=hoy).count(),
        "por_vencer": activos.filter(plazo__gte=hoy, plazo__lte=hoy + datetime.timedelta(days=5)).count(),
        "en_verificacion": qs.filter(estado=Entregable.Estado.VERIFICACION_SENIOR).count(),
        "proximos": activos.order_by("plazo")[:6],
    }
    return render(request, "inicio.html", contexto)
