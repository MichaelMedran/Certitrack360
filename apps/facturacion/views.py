from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.entregables.visibilidad import entregables_visibles

from . import verificacion
from .models import VerificacionFactura


@login_required
@require_POST
def factura(request, pk):
    """POST /entregables/<pk>/factura/: verificar el número de factura (accion=verificar) o justificarlo (accion=justificar)."""
    e = get_object_or_404(entregables_visibles(request.user).select_related("contrato__cliente"), pk=pk)
    accion = request.POST.get("accion")
    try:
        if accion == "verificar":
            v = verificacion.verificar(e, request.user, request.POST.get("numero"))
            if v.correcta:
                messages.success(request, v.detalle.get("mensaje") or "La factura es correcta.")
            else:
                messages.warning(request, f"{v.detalle.get('mensaje', '')} El entregable no pasa a «Aprobado» hasta "
                                          f"verificar un número correcto o hasta que un senior lo justifique.")
        elif accion == "justificar":
            verificacion.justificar(e, request.user, request.POST.get("justificacion"))
            messages.success(request, "Se registró la justificación: la factura ya no impide aprobar el entregable.")
        else:
            raise ValidationError("Elija una acción válida sobre la factura.")
    except PermissionDenied:
        raise
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(verificacion.enlace(e))
