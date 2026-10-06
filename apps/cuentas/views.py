import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from apps.alertas.models import Notificacion
from apps.entregables import urgencia
from apps.entregables.models import Entregable
from apps.entregables.visibilidad import entregables_visibles


@login_required
def inicio(request):
    """Resumen según el rol: lo propio (o lo de sus contratos, o todo), próximos plazos y avisos recientes."""
    hoy = timezone.localdate()
    dias_proximo = urgencia.umbrales()[1]  # el mismo umbral que las alertas y la urgencia
    qs = entregables_visibles(request.user).select_related("contrato__cliente", "junior_asignado")
    activos = qs.exclude(estado=Entregable.Estado.HECHO)
    contexto = {
        "total_activos": activos.count(),
        "vencidos": activos.filter(plazo__lt=hoy).count(),
        "por_vencer": activos.filter(plazo__gte=hoy, plazo__lte=hoy + datetime.timedelta(days=dias_proximo)).count(),
        "dias_proximo": dias_proximo,
        "en_verificacion": qs.filter(estado=Entregable.Estado.VERIFICACION_SENIOR).count(),
        "proximos": activos.order_by("plazo")[:6],
        "recientes": Notificacion.objects.filter(usuario=request.user).select_related("entregable")[:5],
    }
    return render(request, "inicio.html", contexto)
