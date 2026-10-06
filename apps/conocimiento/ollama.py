"""Cliente mínimo del Ollama local. Solo habla con el servidor interno configurado en OLLAMA_URL (RNF-01)."""
import json
import urllib.error
import urllib.request
from urllib.parse import urlparse

from django.conf import settings


class OllamaNoDisponible(Exception):
    """Ollama no responde o devolvió algo inesperado."""


def _post(ruta, cuerpo, timeout):
    base = settings.OLLAMA_URL.rstrip("/")
    if urlparse(base).scheme not in ("http", "https"):
        raise OllamaNoDisponible("OLLAMA_URL debe empezar con http:// o https://")
    peticion = urllib.request.Request(
        base + ruta, data=json.dumps(cuerpo).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            return json.load(respuesta)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise OllamaNoDisponible(str(exc)) from exc


def embeddings(textos):
    """Un vector por texto, calculado con EMBED_MODEL."""
    textos = list(textos)
    respuesta = _post("/api/embed", {"model": settings.EMBED_MODEL, "input": textos}, timeout=60)
    vectores = respuesta.get("embeddings") if isinstance(respuesta, dict) else None
    if not vectores or len(vectores) != len(textos):
        raise OllamaNoDisponible("Ollama no devolvió los embeddings esperados (¿está descargado el modelo %s?)." % settings.EMBED_MODEL)
    return vectores


def responder(mensajes):
    """Respuesta de OLLAMA_MODEL a una conversación [{role, content}, ...]."""
    respuesta = _post("/api/chat", {"model": settings.OLLAMA_MODEL, "stream": False, "messages": mensajes}, timeout=120)
    try:
        return respuesta["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise OllamaNoDisponible("Ollama no devolvió una respuesta válida.") from exc
