def notificaciones(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        from .models import Notificacion

        return {"no_leidas": Notificacion.objects.filter(usuario=user, leida=False).count()}
    return {"no_leidas": 0}
