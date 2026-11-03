"""Enlaces de los avisos (SDD del Sprint 2, §6.1, hito S2-H2).

Un aviso que no es de un entregable (por ejemplo, una ficha de levantamiento que espera confirmación) lleva a su pantalla
con `Notificacion.enlace`. Ese enlace es siempre una ruta interna de CertiTrack 360 y nunca una dirección externa, para que
un aviso no pueda convertirse en una redirección abierta. Se comprueba al guardar, en la base de datos (lo esencial, con
una restricción) y otra vez al mostrarlo.
"""
import re

from django.core.exceptions import ValidationError
from django.utils.http import url_has_allowed_host_and_scheme

MENSAJE_ENLACE = (
    "El enlace del aviso debe ser una ruta interna de CertiTrack 360 que empiece con «/» (por ejemplo, /calendario/); "
    "no se admiten direcciones externas."
)

# Caracteres válidos en una dirección (RFC 3986). Quedan fuera los espacios, los caracteres de control, las comillas y la
# barra invertida: los navegadores descartan tabulaciones y saltos de línea y leen «\» como «/», así que «/\sitio» o
# «/<tab>/sitio» terminarían siendo «//sitio», es decir, otro sitio.
_RUTA = re.compile(r"/[A-Za-z0-9\-._~!$&'()*+,;=:@%/?#]*")


def es_enlace_interno(valor):
    """True si `valor` es una ruta interna relativa: empieza con una sola «/» y no tiene esquema (http:, javascript:…)
    ni anfitrión. La comprobación de Django para redirecciones seguras se aplica además, sin ningún anfitrión permitido."""
    return (
        isinstance(valor, str)
        and _RUTA.fullmatch(valor) is not None
        and not valor.startswith("//")
        and "://" not in valor
        and url_has_allowed_host_and_scheme(valor, allowed_hosts=None)
    )


def validar_enlace_interno(valor):
    """Validador de `Notificacion.enlace`: vacío (el aviso se muestra sin enlace) o una ruta interna."""
    if valor and not es_enlace_interno(valor):
        raise ValidationError(MENSAJE_ENLACE, code="enlace_no_interno")
