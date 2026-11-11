from django.conf import settings
from django.utils.cache import add_never_cache_headers


class SinCacheEnPaginasPrivadas:
    """Las páginas de quien inició sesión no se guardan en la caché del navegador.

    Así, al volver con «Atrás» se ve el estado real (y no una copia vieja del tablero) y no queda información de la
    operación guardada en un equipo compartido. Respeta las respuestas que ya traen su propia política de caché.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        respuesta = self.get_response(request)
        if request.user.is_authenticated and "Cache-Control" not in respuesta:
            add_never_cache_headers(respuesta)
        return respuesta


def politica_de_contenido():
    """Valor de ``Content-Security-Policy`` (SDD del Sprint 3, §7.12 y RNF-16).

    Todo se carga del propio servidor. El único origen externo posible es ``FILEDOC_URL``, y solo para enviar o consultar
    (``form-action`` y ``connect-src``). Los scripts en línea no están permitidos; los atributos ``style`` sí, porque las
    plantillas los usan para anchos de barras y márgenes (no ejecutan código).
    """
    externo = f" {settings.FILEDOC_ORIGEN}" if settings.FILEDOC_ORIGEN else ""
    return "; ".join([
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        f"connect-src 'self'{externo}",
        f"form-action 'self'{externo}",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "object-src 'none'",
    ])


class CabecerasDeSeguridad:
    """Añade ``Content-Security-Policy`` y ``Referrer-Policy: same-origin`` a toda respuesta (RF-51, RNF-16)."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.politica = politica_de_contenido()

    def __call__(self, request):
        respuesta = self.get_response(request)
        respuesta.headers.setdefault("Content-Security-Policy", self.politica)
        respuesta.headers.setdefault("Referrer-Policy", "same-origin")
        return respuesta
