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
