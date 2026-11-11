from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied

from . import bloqueo


class ModelBackendConBloqueo(ModelBackend):
    """Igual que el predeterminado, pero rechaza el intento si el usuario está bloqueado desde esa dirección (RF-51).

    Al lanzar ``PermissionDenied``, Django deja de probar otros métodos y devuelve ``None``: la contraseña ni se revisa.
    Sin ``request`` (pruebas, scripts) no hay dirección y no se aplica el bloqueo.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if request is not None and username:
            hasta = bloqueo.bloqueado_hasta(username, bloqueo.direccion(request))
            if hasta:
                request._ingreso_bloqueado_hasta = hasta  # para que la pantalla lo explique y no se registre como fallo
                raise PermissionDenied("Ingreso bloqueado temporalmente.")
        return super().authenticate(request, username=username, password=password, **kwargs)
