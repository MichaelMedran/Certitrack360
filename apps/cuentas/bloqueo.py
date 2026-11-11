"""Bloqueo temporal por intentos de ingreso fallidos (SDD del Sprint 3, §7.12, RF-51).

Tras ``LOGIN_MAX_INTENTOS`` fallos seguidos de un mismo usuario desde una misma dirección, el ingreso queda bloqueado
``LOGIN_BLOQUEO_MINUTOS``: el intento siguiente (el sexto, con el valor por defecto) se rechaza aunque la contraseña sea
correcta. Un ingreso acertado reinicia la cuenta. Los intentos rechazados por el bloqueo no se registran, así que no lo alargan.
"""
import datetime

from django.conf import settings
from django.utils import timezone

from .models import IntentoIngreso

CONSERVAR_DIAS = 30


def normalizar(usuario_texto):
    return (usuario_texto or "").strip().lower()[:150]


def direccion(request):
    """Dirección del cliente. No se confía en X-Forwarded-For: cualquiera puede escribirla para esquivar el bloqueo."""
    return (request.META.get("REMOTE_ADDR") or "")[:45] if request is not None else ""


def bloqueado_hasta(usuario_texto, ip, ahora=None):
    """Instante en que termina el bloqueo, o ``None`` si el usuario puede intentar ingresar."""
    ahora = ahora or timezone.now()
    base = IntentoIngreso.objects.filter(usuario_texto=normalizar(usuario_texto), ip=ip)
    ultimo_acierto = base.filter(exitoso=True).order_by("-fecha").values_list("fecha", flat=True).first()
    fallos = base.filter(exitoso=False, fecha__gt=ahora - datetime.timedelta(minutes=settings.LOGIN_BLOQUEO_MINUTOS))
    if ultimo_acierto:
        fallos = fallos.filter(fecha__gt=ultimo_acierto)
    recientes = list(fallos.order_by("-fecha").values_list("fecha", flat=True)[: settings.LOGIN_MAX_INTENTOS])
    if len(recientes) < settings.LOGIN_MAX_INTENTOS:
        return None
    # El bloqueo termina cuando el más antiguo de los últimos fallos sale de la ventana.
    return recientes[-1] + datetime.timedelta(minutes=settings.LOGIN_BLOQUEO_MINUTOS)


def registrar(usuario_texto, ip, exitoso):
    IntentoIngreso.objects.create(usuario_texto=normalizar(usuario_texto), ip=ip, exitoso=exitoso)
    IntentoIngreso.objects.filter(fecha__lt=timezone.now() - datetime.timedelta(days=CONSERVAR_DIAS)).delete()
