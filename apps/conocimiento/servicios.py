"""Búsqueda sobre lecciones aprendidas y respuesta con Ollama local.

La recuperación es léxica (TF-IDF simplificado, sin dependencias ni servicios externos).
Si más adelante se aprueba ChromaDB o pgvector, solo hay que reemplazar `buscar`.
"""
import json
import math
import re
import unicodedata
import urllib.error
import urllib.request

from django.conf import settings

from apps.entregables.models import Entregable, Observacion
from apps.entregables.visibilidad import entregables_visibles

from .models import LeccionAprendida

PALABRAS_VACIAS = set(
    "a al algo con como cual de del el ella en es esta este la las lo los me mi no para por que se si su sus "
    "un una uno y o u ya hay fue ser son tiene tienen cuando donde sobre mas muy".split()
)


def _tokens(texto):
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    palabras = re.findall(r"[a-z0-9]+", texto)
    # recorte simple de plurales para igualar «informes» con «informe»
    return [p[:-1] if len(p) > 4 and p.endswith("s") else p for p in palabras if p not in PALABRAS_VACIAS and len(p) > 1]


def indexar_lecciones():
    """Crea lecciones desde observaciones resueltas de entregables cerrados. Devuelve cuántas se crearon."""
    nuevas = 0
    pendientes = Observacion.objects.filter(
        resuelta=True, entregable__estado=Entregable.Estado.HECHO, leccion__isnull=True
    ).select_related("entregable__contrato__cliente")
    for o in pendientes:
        LeccionAprendida.objects.create(
            entregable_origen=o.entregable, observacion_origen=o, cliente=o.entregable.contrato.cliente,
            tipo_error=o.tipo_error, problema=o.descripcion, solucion=o.solucion,
        )
        nuevas += 1
    return nuevas


def buscar(pregunta, limite=3):
    lecciones = list(LeccionAprendida.objects.select_related("cliente", "entregable_origen__contrato"))
    consulta = set(_tokens(pregunta))
    if not consulta or not lecciones:
        return []
    docs = [
        _tokens(f"{l.problema} {l.solucion} {l.get_tipo_error_display()} {l.cliente.nombre}") for l in lecciones
    ]
    n = len(docs)
    puntajes = []
    for leccion, toks in zip(lecciones, docs):
        puntaje = 0.0
        for t in consulta:
            frecuencia = toks.count(t)
            if frecuencia:
                df = sum(1 for d in docs if t in d)
                puntaje += (1 + math.log(frecuencia)) * (math.log((n + 1) / df) + 1)
        if puntaje > 0:
            puntajes.append((puntaje, leccion))
    puntajes.sort(key=lambda x: -x[0])
    return [l for _, l in puntajes[:limite]]


def preguntar_ollama(pregunta, lecciones):
    """Devuelve (texto, None) o (None, mensaje_de_error). Solo habla con el Ollama local."""
    contexto = "\n\n".join(
        f"[Caso {i}] Cliente: {l.cliente}. Error: {l.get_tipo_error_display()}. Problema: {l.problema} Solución: {l.solucion}"
        for i, l in enumerate(lecciones, 1)
    )
    cuerpo = json.dumps({
        "model": settings.OLLAMA_MODELO, "stream": False,
        "messages": [
            {"role": "system", "content": "Eres un asistente de CERTICOM. Responde en español, breve, usando SOLO los casos dados. Cita el número de caso, por ejemplo [Caso 1]."},
            {"role": "user", "content": f"Casos:\n{contexto}\n\nPregunta: {pregunta}"},
        ],
    }).encode()
    req = urllib.request.Request(
        settings.OLLAMA_URL.rstrip("/") + "/api/chat", data=cuerpo, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)["message"]["content"], None
    except (urllib.error.URLError, OSError, KeyError, ValueError):
        return None, "El asistente de redacción (Ollama) no está disponible en el servidor. Se muestran los casos encontrados."


def responder(pregunta, usuario):
    lecciones = buscar(pregunta)
    visibles = set(entregables_visibles(usuario).values_list("pk", flat=True))
    casos = [{"leccion": l, "enlace": l.entregable_origen_id in visibles} for l in lecciones]
    texto, aviso = (None, None)
    if lecciones:
        texto, aviso = preguntar_ollama(pregunta, lecciones)
    return {"casos": casos, "respuesta": texto, "aviso": aviso}
