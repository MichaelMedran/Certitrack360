"""Ayudantes para las respuestas parciales de HTMX."""
from django.utils.cache import patch_vary_headers


def es_htmx(request):
    return request.headers.get("HX-Request") == "true"


def pide_parcial(request):
    """HTMX pide solo el fragmento, salvo al restaurar el historial del navegador (ahí necesita la página completa)."""
    return es_htmx(request) and request.headers.get("HX-History-Restore-Request") != "true"


def con_vary(respuesta):
    """La misma dirección responde distinto a HTMX y al navegador: que ninguna caché las confunda."""
    patch_vary_headers(respuesta, ("HX-Request",))
    return respuesta
