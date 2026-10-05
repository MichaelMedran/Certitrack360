from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import Notificacion


@login_required
def lista(request):
    notificaciones = Notificacion.objects.filter(usuario=request.user).select_related("entregable")[:100]
    return render(request, "alertas/lista.html", {"notificaciones": notificaciones})


@login_required
@require_POST
def marcar_leidas(request):
    Notificacion.objects.filter(usuario=request.user, leida=False).update(leida=True)
    return redirect("notificaciones")
