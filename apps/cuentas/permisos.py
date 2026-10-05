"""Decoradores y mixins de acceso por rol."""
from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


def solo_gestion(vista):
    """Solo Gerente y Admin."""

    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        if not request.user.es_gerente_o_admin:
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


def solo_senior_o_superior(vista):
    @wraps(vista)
    def envoltura(request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        if not request.user.puede_crear_entregables:
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura


class GestionRequeridaMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.es_gerente_o_admin:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
