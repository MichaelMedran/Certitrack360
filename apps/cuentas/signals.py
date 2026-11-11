from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from . import bloqueo


@receiver(user_login_failed)
def registrar_fallo(sender, credentials, request=None, **kwargs):
    if request is None or getattr(request, "_ingreso_bloqueado_hasta", None):
        return  # rechazado por el propio bloqueo: no se cuenta, para no alargarlo
    bloqueo.registrar(credentials.get("username", ""), bloqueo.direccion(request), exitoso=False)


@receiver(user_logged_in)
def registrar_acierto(sender, request, user, **kwargs):
    if request is not None:
        bloqueo.registrar(user.get_username(), bloqueo.direccion(request), exitoso=True)
