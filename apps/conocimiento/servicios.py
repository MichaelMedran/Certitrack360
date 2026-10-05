"""Asistente de lecciones aprendidas (SDD §12.7, RF-19).

Flujo: al cerrar un entregable (HECHO) cada observación resuelta con solución se convierte en una lección; un comando
(y la tarea programada) calcula sus embeddings con Ollama y los guarda en el índice vectorial local (la propia tabla de
lecciones); la consulta busca por significado, arma un prompt solo con esos casos y cita su origen.

Si Ollama no está disponible o aún no hay embeddings, la búsqueda cae a coincidencia de palabras y la pantalla lo avisa:
el resto de la plataforma no depende del modelo (RNF-09).
"""
import math
import re
import unicodedata

from django.conf import settings
from django.db.models import Q

from apps.entregables.models import Entregable, Observacion
from apps.entregables.visibilidad import entregables_visibles

from . import ollama
from .models import LeccionAprendida

PALABRAS_VACIAS = set(
    "a al algo con como cual de del el ella en es esta este la las lo los me mi no para por que se si su sus "
    "un una uno y o u ya hay fue ser son tiene tienen cuando donde sobre mas muy".split()
)

AVISO_SIN_OLLAMA = (
    "El asistente de lenguaje (Ollama) no está disponible en el servidor. "
    "Se muestran los casos encontrados por coincidencia de palabras."
)
AVISO_SIN_INDICE = (
    "Las lecciones todavía no están indexadas (ejecute «python manage.py indexar_lecciones»). "
    "Se muestran los casos encontrados por coincidencia de palabras."
)
AVISO_SIN_REDACCION = "El asistente de redacción (Ollama) no está disponible en el servidor. Se muestran los casos encontrados."


# ---------------------------------------------------------------- generación e indexación

def generar_lecciones(entregable):
    """Una lección por cada observación resuelta (con solución) del entregable. No duplica. Devuelve cuántas creó."""
    pendientes = (
        entregable.observaciones.filter(resuelta=True, leccion__isnull=True).exclude(solucion__regex=r"^\s*$")
    )
    cliente = entregable.contrato.cliente
    nuevas = 0
    for o in pendientes:
        LeccionAprendida.objects.create(
            entregable_origen=entregable, observacion_origen=o, cliente=cliente, tipo_error=o.tipo_error,
            problema=o.descripcion, solucion=o.solucion,
        )
        nuevas += 1
    return nuevas


def generar_lecciones_pendientes():
    """Recorre los entregables cerrados (por si se resolvió alguna observación después de cerrarlos)."""
    return sum(
        generar_lecciones(e)
        for e in Entregable.objects.filter(estado=Entregable.Estado.HECHO).select_related("contrato__cliente")
    )


def indexar_embeddings():
    """Calcula los embeddings que faltan (o los del modelo anterior). Devuelve (cantidad, aviso o None)."""
    pendientes = list(
        LeccionAprendida.objects.filter(Q(embedding__isnull=True) | ~Q(embedding_modelo=settings.EMBED_MODEL))
    )
    if not pendientes:
        return 0, None
    try:
        vectores = ollama.embeddings([leccion.texto_indexable for leccion in pendientes])
    except ollama.OllamaNoDisponible as exc:
        return 0, f"No se pudieron calcular los embeddings: {exc}"
    for leccion, vector in zip(pendientes, vectores):
        leccion.embedding, leccion.embedding_modelo = vector, settings.EMBED_MODEL
        leccion.save(update_fields=["embedding", "embedding_modelo"])
    return len(pendientes), None


def indexar_lecciones():
    """Genera las lecciones que falten y calcula sus embeddings. Devuelve (nuevas, indexadas, aviso)."""
    nuevas = generar_lecciones_pendientes()
    indexadas, aviso = indexar_embeddings()
    return nuevas, indexadas, aviso


# ---------------------------------------------------------------- búsqueda

def coseno(a, b):
    producto = sum(x * y for x, y in zip(a, b))
    norma = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return producto / norma if norma else 0.0


class SinIndice(Exception):
    """Todavía no hay lecciones con embeddings."""


def buscar_semantico(pregunta, limite=3):
    """Lecciones más cercanas por significado, descartando las poco relacionadas (ASSISTANT_MIN_SIMILARITY)."""
    indexadas = list(
        LeccionAprendida.objects.filter(embedding__isnull=False, embedding_modelo=settings.EMBED_MODEL)
        .select_related("cliente", "entregable_origen__contrato")
    )
    if not indexadas:
        raise SinIndice
    [consulta] = ollama.embeddings([pregunta])
    puntuadas = sorted(((coseno(consulta, leccion.embedding), leccion) for leccion in indexadas), key=lambda p: -p[0])
    return [leccion for puntaje, leccion in puntuadas[:limite] if puntaje >= settings.ASSISTANT_MIN_SIMILARITY]


def _tokens(texto):
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    palabras = re.findall(r"[a-z0-9]+", texto)
    # recorte simple de plurales para igualar «informes» con «informe»
    return [p[:-1] if len(p) > 4 and p.endswith("s") else p for p in palabras if p not in PALABRAS_VACIAS and len(p) > 1]


def buscar_lexico(pregunta, limite=3):
    """Respaldo sin modelo: coincidencia de palabras (TF-IDF simplificado)."""
    lecciones = list(LeccionAprendida.objects.select_related("cliente", "entregable_origen__contrato"))
    consulta = set(_tokens(pregunta))
    if not consulta or not lecciones:
        return []
    docs = [_tokens(f"{l.problema} {l.solucion} {l.get_tipo_error_display()} {l.cliente.nombre}") for l in lecciones]
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


# ---------------------------------------------------------------- consulta

def _prompt(pregunta, lecciones):
    casos = "\n\n".join(
        f"[Caso {i}] Cliente: {l.cliente}. Error: {l.get_tipo_error_display()}. Problema: {l.problema} Solución: {l.solucion}"
        for i, l in enumerate(lecciones, 1)
    )
    return [
        {"role": "system", "content": (
            "Eres un asistente interno de CERTICOM. Responde en español, de forma breve, usando SOLO los casos dados. "
            "Cita el número de caso, por ejemplo [Caso 1]. Si los casos no responden la pregunta, dilo sin inventar."
        )},
        {"role": "user", "content": f"Casos:\n{casos}\n\nPregunta: {pregunta}"},
    ]


def responder(pregunta, usuario):
    """Resultado de una consulta: casos citados (con enlace solo si el usuario puede ver el entregable de origen),
    la respuesta redactada por el modelo (si está disponible) y un aviso cuando algo se degradó."""
    aviso = None
    try:
        lecciones = buscar_semantico(pregunta)
    except SinIndice:
        lecciones, aviso = buscar_lexico(pregunta), AVISO_SIN_INDICE
    except ollama.OllamaNoDisponible:
        lecciones, aviso = buscar_lexico(pregunta), AVISO_SIN_OLLAMA

    respuesta = None
    if lecciones:
        try:
            respuesta = ollama.responder(_prompt(pregunta, lecciones))
        except ollama.OllamaNoDisponible:
            aviso = aviso or AVISO_SIN_REDACCION

    visibles = set(entregables_visibles(usuario).values_list("pk", flat=True))
    casos = [{"leccion": l, "enlace": l.entregable_origen_id in visibles} for l in lecciones]
    return {"casos": casos, "respuesta": respuesta, "aviso": aviso}
