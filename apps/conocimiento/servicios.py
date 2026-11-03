"""Asistente de lecciones aprendidas y procedimientos aprobados (SDD §12.7, RF-19; SDD Sprint 2 §7.11, RF-37: HU-10).

Flujo: al cerrar un entregable (HECHO) cada observación resuelta con solución se convierte en una lección; además, el
gerente y el admin cargan y aprueban procedimientos en `/procedimientos/`. El comando `indexar_lecciones` (y la tarea
programada) calcula los embeddings de ambos con Ollama y los guarda en el índice vectorial local; la consulta busca por
significado en procedimientos vigentes y lecciones, arma un prompt solo con esas fuentes y las cita.

Si Ollama no está disponible o aún no hay embeddings, la búsqueda cae a coincidencia de palabras y la pantalla lo avisa:
el resto de la plataforma no depende del modelo (RNF-09).
"""
import math
import re
import unicodedata

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.clientes.models import Contrato, LineaServicio
from apps.entregables.filtros import entero
from apps.entregables.models import Entregable
from apps.entregables.visibilidad import entregables_visibles
from apps.repositorio.models import DocumentoRepositorio
from apps.repositorio.visibilidad import documentos_visibles

from . import ollama
from .models import ConsultaAsistente, LeccionAprendida, Procedimiento

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
    """Calcula los embeddings que faltan de lecciones y procedimientos vigentes. Devuelve (cantidad, aviso o None)."""
    condicion = Q(embedding__isnull=True) | ~Q(embedding_modelo=settings.EMBED_MODEL)
    pendientes = list(LeccionAprendida.objects.filter(condicion)) + list(
        Procedimiento.objects.filter(vigente=True).filter(condicion)
    )
    if not pendientes:
        return 0, None
    try:
        vectores = ollama.embeddings([item.texto_indexable for item in pendientes])
    except ollama.OllamaNoDisponible as exc:
        return 0, f"No se pudieron calcular los embeddings: {exc}"
    for item, vector in zip(pendientes, vectores):
        item.embedding, item.embedding_modelo = vector, settings.EMBED_MODEL
        item.save(update_fields=["embedding", "embedding_modelo"])
    return len(pendientes), None


def indexar_lecciones():
    """Genera las lecciones que falten y calcula los embeddings pendientes. Devuelve (nuevas, indexadas, aviso)."""
    nuevas = generar_lecciones_pendientes()
    indexadas, aviso = indexar_embeddings()
    return nuevas, indexadas, aviso


# ---------------------------------------------------------------- búsqueda

def coseno(a, b):
    producto = sum(x * y for x, y in zip(a, b))
    norma = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return producto / norma if norma else 0.0


class SinIndice(Exception):
    """Todavía no hay lecciones ni procedimientos con embeddings."""


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


def buscar_procedimientos_semantico(pregunta, limite=3):
    """Procedimientos vigentes más cercanos por significado (ASSISTANT_MIN_SIMILARITY)."""
    indexados = list(
        Procedimiento.objects.filter(
            vigente=True, embedding__isnull=False, embedding_modelo=settings.EMBED_MODEL
        ).select_related("linea_servicio", "aprobado_por", "documento")
    )
    if not indexados:
        raise SinIndice
    [consulta] = ollama.embeddings([pregunta])
    puntuados = sorted(((coseno(consulta, proc.embedding), proc) for proc in indexados), key=lambda p: -p[0])
    return [proc for puntaje, proc in puntuados[:limite] if puntaje >= settings.ASSISTANT_MIN_SIMILARITY]


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


def buscar_procedimientos_lexico(pregunta, limite=3, solo_sin_indice=False):
    """Respaldo por palabras para procedimientos vigentes (TF-IDF simplificado)."""
    qs = Procedimiento.objects.filter(vigente=True).select_related("linea_servicio", "aprobado_por", "documento")
    if solo_sin_indice:
        qs = qs.filter(Q(embedding__isnull=True) | ~Q(embedding_modelo=settings.EMBED_MODEL))
    procedimientos = list(qs)
    consulta = set(_tokens(pregunta))
    if not consulta or not procedimientos:
        return []
    docs = [
        _tokens(f"{p.titulo} {p.contenido} {p.linea_servicio.nombre if p.linea_servicio else ''}")
        for p in procedimientos
    ]
    n = len(docs)
    puntajes = []
    for proc, toks in zip(procedimientos, docs):
        puntaje = 0.0
        for t in consulta:
            frecuencia = toks.count(t)
            if frecuencia:
                df = sum(1 for d in docs if t in d)
                puntaje += (1 + math.log(frecuencia)) * (math.log((n + 1) / df) + 1)
        if puntaje > 0:
            puntajes.append((puntaje, proc))
    puntajes.sort(key=lambda x: -x[0])
    return [p for _, p in puntajes[:limite]]


# ---------------------------------------------------------------- gestión de procedimientos y valoración

def guardar_procedimiento(
    autor,
    *,
    titulo,
    contenido,
    linea_servicio=None,
    documento=None,
    vigente=True,
    procedimiento=None,
):
    """Crea o edita un procedimiento aprobado (solo gerente y admin: §7.11 y §8)."""
    if not getattr(autor, "es_gerente_o_admin", False):
        raise PermissionDenied("Solo el gerente y el administrador pueden cargar o modificar procedimientos.")

    titulo_limpio = (titulo or "").strip()[:200]
    contenido_limpio = (contenido or "").strip()
    errores = []
    if not titulo_limpio:
        errores.append("Falta el título del procedimiento.")
    if not contenido_limpio:
        errores.append("Falta el contenido del procedimiento.")
    if errores:
        raise ValidationError(errores)

    linea_obj = None
    if isinstance(linea_servicio, LineaServicio):
        linea_obj = linea_servicio
    elif linea_servicio not in (None, ""):
        lid = entero(linea_servicio)
        if lid is None:
            raise ValidationError("La línea de servicio seleccionada no es válida.")
        linea_obj = LineaServicio.objects.filter(pk=lid).first()
        if linea_obj is None:
            raise ValidationError("La línea de servicio seleccionada no existe.")

    doc_obj = None
    if isinstance(documento, DocumentoRepositorio):
        doc_obj = documento
    elif documento not in (None, ""):
        did = entero(documento)
        if did is None:
            raise ValidationError("El documento del repositorio seleccionado no es válido.")
        doc_obj = DocumentoRepositorio.objects.filter(pk=did).first()
        if doc_obj is None:
            raise ValidationError("El documento del repositorio seleccionado no existe.")

    if procedimiento is None:
        return Procedimiento.objects.create(
            titulo=titulo_limpio,
            contenido=contenido_limpio,
            linea_servicio=linea_obj,
            documento=doc_obj,
            aprobado_por=autor,
            aprobado_en=timezone.now(),
            vigente=bool(vigente),
        )

    cambio_texto = procedimiento.titulo != titulo_limpio or procedimiento.contenido != contenido_limpio
    procedimiento.titulo = titulo_limpio
    procedimiento.contenido = contenido_limpio
    procedimiento.linea_servicio = linea_obj
    procedimiento.documento = doc_obj
    procedimiento.vigente = bool(vigente)
    procedimiento.aprobado_por = autor
    procedimiento.aprobado_en = timezone.now()
    if cambio_texto:
        procedimiento.embedding = None
        procedimiento.embedding_modelo = ""
    procedimiento.save()
    return procedimiento


def valorar_consulta(consulta, usuario, util):
    """Guarda la valoración «¿Le sirvió?» de una consulta propia (RF-37, HU-10 criterio 5)."""
    if not getattr(usuario, "is_authenticated", False) or consulta.usuario_id != usuario.pk:
        raise PermissionDenied("Solo puede valorar sus propias consultas.")
    if isinstance(util, str):
        v = util.strip().lower()
        if v in ("si", "sí", "1", "true"):
            valor = True
        elif v in ("no", "0", "false"):
            valor = False
        else:
            raise ValidationError("Indique si la respuesta le sirvió (Sí o No).")
    elif isinstance(util, bool):
        valor = util
    else:
        raise ValidationError("Indique si la respuesta le sirvió (Sí o No).")
    consulta.util = valor
    consulta.save(update_fields=["util"])
    return consulta


def senior_escalamiento(usuario):
    """Nombre del senior responsable del contrato del usuario, para orientar el escalamiento cuando no hay fuentes."""
    if not getattr(usuario, "is_authenticated", False):
        return None
    contrato = (
        Contrato.objects.filter(activo=True, juniors=usuario)
        .select_related("senior_responsable")
        .order_by("id")
        .first()
    )
    if contrato and contrato.senior_responsable:
        return contrato.senior_responsable.nombre
    entregable = (
        Entregable.objects.filter(junior_asignado=usuario)
        .select_related("senior_revisor")
        .order_by("-id")
        .first()
    )
    if entregable and entregable.senior_revisor:
        return entregable.senior_revisor.nombre
    return None


# ---------------------------------------------------------------- consulta

def _prompt(pregunta, lecciones, procedimientos=None):
    procedimientos = list(procedimientos or [])
    partes = []
    if procedimientos:
        texto_proc = "\n\n".join(
            f"[Procedimiento {i}] Título: {p.titulo}. Línea: {p.linea_servicio.nombre if p.linea_servicio else 'Todas'}. Contenido: {p.contenido}"
            for i, p in enumerate(procedimientos, 1)
        )
        partes.append(f"Procedimientos aprobados:\n{texto_proc}")
    if lecciones or not procedimientos:
        casos = "\n\n".join(
            f"[Caso {i}] Cliente: {l.cliente}. Error: {l.get_tipo_error_display()}. Problema: {l.problema} Solución: {l.solucion}"
            for i, l in enumerate(lecciones, 1)
        )
        partes.append(f"Casos:\n{casos}")
    cuerpo = "\n\n".join(partes)
    extra_proc = (
        " Si se incluyen procedimientos aprobados, úsalos también y cítalos como [Procedimiento 1]."
        if procedimientos
        else ""
    )
    return [
        {"role": "system", "content": (
            "Eres un asistente interno de CERTICOM. Responde en español, de forma breve, usando SOLO los casos dados."
            f"{extra_proc} "
            "Cita el número de caso, por ejemplo [Caso 1]. Si los casos no responden la pregunta, dilo sin inventar."
        )},
        {"role": "user", "content": f"{cuerpo}\n\nPregunta: {pregunta}"},
    ]


def _enriquecer_procedimientos(procedimientos, usuario):
    docs_vis = (
        set(documentos_visibles(usuario).values_list("pk", flat=True))
        if getattr(usuario, "is_authenticated", False)
        else set()
    )
    for p in procedimientos:
        p.documento_visible = bool(p.documento_id and p.documento_id in docs_vis)
    return procedimientos


def responder(pregunta, usuario, guardar_historial=True):
    """Resultado de una consulta: procedimientos vigentes y casos citados (con enlace solo si el usuario puede ver el
    entregable de origen, decisión C6), la respuesta redactada por el modelo y el registro en `ConsultaAsistente`."""
    aviso = None
    hay_lecciones_idx = LeccionAprendida.objects.filter(
        embedding__isnull=False, embedding_modelo=settings.EMBED_MODEL
    ).exists()
    hay_proc_idx = Procedimiento.objects.filter(
        vigente=True, embedding__isnull=False, embedding_modelo=settings.EMBED_MODEL
    ).exists()

    try:
        if not hay_lecciones_idx and not hay_proc_idx:
            raise SinIndice
        lecciones = buscar_semantico(pregunta) if hay_lecciones_idx else buscar_lexico(pregunta)
        if hay_proc_idx:
            procedimientos = buscar_procedimientos_semantico(pregunta)
            sin_idx = buscar_procedimientos_lexico(pregunta, solo_sin_indice=True)
            vistos = {p.pk for p in procedimientos}
            for p in sin_idx:
                if p.pk not in vistos and len(procedimientos) < 3:
                    procedimientos.append(p)
        else:
            procedimientos = buscar_procedimientos_lexico(pregunta)
    except SinIndice:
        lecciones = buscar_lexico(pregunta)
        procedimientos = buscar_procedimientos_lexico(pregunta)
        aviso = AVISO_SIN_INDICE
    except ollama.OllamaNoDisponible:
        lecciones = buscar_lexico(pregunta)
        procedimientos = buscar_procedimientos_lexico(pregunta)
        aviso = AVISO_SIN_OLLAMA

    respuesta = None
    if lecciones or procedimientos:
        try:
            respuesta = ollama.responder(_prompt(pregunta, lecciones, procedimientos))
        except ollama.OllamaNoDisponible:
            aviso = aviso or AVISO_SIN_REDACCION

    visibles = set(entregables_visibles(usuario).values_list("pk", flat=True))
    casos = [{"leccion": l, "enlace": l.entregable_origen_id in visibles} for l in lecciones]
    procedimientos = _enriquecer_procedimientos(procedimientos, usuario)

    consulta = None
    pregunta_limpia = (pregunta or "").strip()
    if guardar_historial and getattr(usuario, "is_authenticated", False) and pregunta_limpia:
        consulta = ConsultaAsistente.objects.create(
            usuario=usuario,
            pregunta=pregunta_limpia[:500],
            respuesta=respuesta or "",
            fuentes={
                "procedimientos": [p.pk for p in procedimientos],
                "lecciones": [l.pk for l in lecciones],
            },
        )

    return {
        "casos": casos,
        "procedimientos": procedimientos,
        "respuesta": respuesta,
        "aviso": aviso,
        "consulta": consulta,
        "senior_escalamiento": senior_escalamiento(usuario),
    }


def reconstruir_consulta(consulta, usuario):
    """Reconstruye el contexto de una `ConsultaAsistente` guardada para «Ver de nuevo» sin duplicar el historial."""
    fuentes = consulta.fuentes or {}
    proc_ids = [entero(x) for x in fuentes.get("procedimientos", []) if entero(x) is not None]
    lec_ids = [entero(x) for x in fuentes.get("lecciones", []) if entero(x) is not None]

    proc_map = {
        p.pk: p
        for p in Procedimiento.objects.filter(pk__in=proc_ids).select_related(
            "linea_servicio", "aprobado_por", "documento"
        )
    }
    procedimientos = [proc_map[pk] for pk in proc_ids if pk in proc_map]
    procedimientos = _enriquecer_procedimientos(procedimientos, usuario)

    lec_map = {
        l.pk: l
        for l in LeccionAprendida.objects.filter(pk__in=lec_ids).select_related(
            "cliente", "entregable_origen__contrato"
        )
    }
    lecciones = [lec_map[pk] for pk in lec_ids if pk in lec_map]
    visibles = set(entregables_visibles(usuario).values_list("pk", flat=True))
    casos = [{"leccion": l, "enlace": l.entregable_origen_id in visibles} for l in lecciones]

    return {
        "pregunta": consulta.pregunta,
        "casos": casos,
        "procedimientos": procedimientos,
        "respuesta": consulta.respuesta or None,
        "aviso": None,
        "consulta": consulta,
        "senior_escalamiento": senior_escalamiento(usuario),
        "buscado": True,
    }
