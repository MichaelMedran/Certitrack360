"""Servicio del buscador global con visibilidad estricta por rol (SDD del Sprint 2, RF-36: HU-21 y RNF-12, §7.10).

Reglas:
- Insensible a mayúsculas y tildes (`"tecnico"` encuentra `"Informe técnico"`, `"ANDINO"` encuentra `"Banco Andino"`).
- Mínimo 2 caracteres (`len(q.strip()) >= 2`).
- Cinco grupos de resultados (Entregables, Contratos, Clientes, Adjuntos y Repositorio), cada uno acotado por su
  queryset de visibilidad y limitado a `settings.BUSCADOR_LIMITE` (por defecto 20) por grupo.
- Filtros (`desde`, `hasta`, `tipo_documento`, `estado`, `cliente`) que reducen los grupos correspondientes y nunca
  amplían la visibilidad. Los valores fuera de rango o fechas mal formadas se ignoran sin error 500.
"""
import datetime
import re
import time
import unicodedata

from django.conf import settings
from django.db.models import Prefetch, Q

from apps.clientes.models import Cliente, Contrato
from apps.entregables import subestado
from apps.entregables.filtros import entero
from apps.entregables.models import Adjunto, Entregable
from apps.entregables.tipos import TipoAdjunto
from apps.entregables.visibilidad import entregables_visibles
from apps.repositorio.models import DocumentoRepositorio, VersionDocumento
from apps.repositorio.visibilidad import documentos_visibles

MINIMO_CARACTERES = 2

_CLASES_VOCALES = {
    "a": "[aáàäâãAÁÀÄÂÃ]",
    "e": "[eéèëêEÉÈËÊ]",
    "i": "[iíìïîIÍÌÏÎ]",
    "o": "[oóòöôõOÓÒÖÔÕ]",
    "u": "[uúùüûUÚÙÜÛ]",
    "n": "[nñNÑ]",
    "c": "[cçCÇ]",
}

TITULOS_FILTROS = [
    ("desde", "Desde"),
    ("hasta", "Hasta"),
    ("tipo_documento", "Tipo de documento"),
    ("estado", "Estado"),
    ("cliente", "Cliente"),
]


def sin_tildes(texto):
    """Normaliza un texto quitando marcas diacríticas (salvo la virgulilla de la ñ, que se trata en `_CLASES_VOCALES`)."""
    salida = []
    for ch in (texto or ""):
        if ch in ("ñ", "Ñ", "ç", "Ç"):
            salida.append(ch.lower())
            continue
        descomp = unicodedata.normalize("NFD", ch)
        base = "".join(c for c in descomp if unicodedata.category(c) != "Mn")
        salida.append(base.lower())
    return "".join(salida)


def patron_insensible(termino):
    """Construye una expresión regular insensible a mayúsculas y tildes para usar con `__iregex`."""
    limpio = sin_tildes(termino)
    partes = []
    for ch in limpio:
        if ch in _CLASES_VOCALES:
            partes.append(_CLASES_VOCALES[ch])
        else:
            partes.append(re.escape(ch))
    return "".join(partes)


def _condicion_campos(campos, termino):
    """Condición Q que exige que todas las palabras de `termino` aparezcan (sin distinguir mayúsculas ni tildes)."""
    palabras = [p for p in (termino or "").split() if p]
    if not palabras:
        return Q(pk__in=[])
    cond_total = Q()
    for palabra in palabras:
        pat = patron_insensible(palabra)
        cond_palabra = Q()
        for campo in campos:
            cond_palabra |= Q(**{f"{campo}__iregex": pat})
        cond_total &= cond_palabra
    return cond_total


def _fecha(valor):
    try:
        return datetime.date.fromisoformat((valor or "").strip())
    except (TypeError, ValueError):
        return None


def contratos_visibles_busqueda(usuario):
    """Contratos visibles en el buscador según el rol (§7.10)."""
    if not getattr(usuario, "is_authenticated", False):
        return Contrato.objects.none()
    if usuario.es_gerente_o_admin:
        return Contrato.objects.all()
    ent_vis = entregables_visibles(usuario).values("contrato_id")
    if usuario.es_senior:
        return Contrato.objects.filter(Q(senior_responsable=usuario) | Q(pk__in=ent_vis)).distinct()
    return Contrato.objects.filter(Q(juniors=usuario) | Q(pk__in=ent_vis)).distinct()


def clientes_visibles_busqueda(usuario):
    """Clientes visibles en el buscador según el rol (§7.10)."""
    if not getattr(usuario, "is_authenticated", False):
        return Cliente.objects.none()
    if usuario.es_gerente_o_admin:
        return Cliente.objects.all()
    contratos_vis = contratos_visibles_busqueda(usuario).values("cliente_id")
    ent_clientes = entregables_visibles(usuario).values("contrato__cliente_id")
    return Cliente.objects.filter(Q(pk__in=contratos_vis) | Q(pk__in=ent_clientes)).distinct()


def tipos_documento_opciones():
    """Unión de tipos de documento del repositorio y tipos de adjunto de los entregables."""
    vistos = {}
    for codigo, etiqueta in DocumentoRepositorio.TipoDocumento.choices:
        vistos[codigo] = str(etiqueta)
    for codigo, etiqueta in TipoAdjunto.choices:
        if codigo not in vistos:
            vistos[codigo] = str(etiqueta)
    return list(vistos.items())


def opciones_filtros(usuario):
    return {
        "clientes": clientes_visibles_busqueda(usuario).order_by("nombre"),
        "estados": subestado.estados_con_subestado(),
        "tipos_documento": tipos_documento_opciones(),
    }


def chips_filtros(params, activos, opciones):
    nombres = {
        "cliente": {c.pk: c.nombre for c in opciones["clientes"]},
        "estado": dict(opciones["estados"]),
        "tipo_documento": dict(opciones["tipos_documento"]),
    }
    salida = []
    for clave, titulo in TITULOS_FILTROS:
        if clave in activos:
            resto = params.copy()
            resto.pop(clave, None)
            if clave == "tipo_documento":
                resto.pop("tipo", None)
            if clave in ("desde", "hasta"):
                valor = activos[clave].strftime("%d/%m/%Y")
            else:
                valor = nombres[clave].get(activos[clave], "no disponible")
            salida.append({"clave": clave, "texto": f"{titulo}: {valor}", "quitar": "?" + resto.urlencode()})
    return salida


def buscar(usuario, params=None):
    """Ejecuta la búsqueda global acotada por rol y filtros, limitando cada grupo a `settings.BUSCADOR_LIMITE`."""
    t0 = time.perf_counter()
    params = params or {}
    limite = settings.BUSCADOR_LIMITE

    q = " ".join((params.get("q") or "").split())[:150]
    activos = {}

    desde = _fecha(params.get("desde"))
    if desde is not None:
        activos["desde"] = desde

    hasta = _fecha(params.get("hasta"))
    if hasta is not None:
        activos["hasta"] = hasta

    tipos_validos = dict(tipos_documento_opciones())
    tipo_doc = (params.get("tipo_documento") or params.get("tipo") or "").strip().upper()
    if tipo_doc in tipos_validos:
        activos["tipo_documento"] = tipo_doc
    else:
        tipo_doc = ""

    estado = (params.get("estado") or "").strip()
    if estado in Entregable.Estado.values or estado == subestado.VALOR:
        activos["estado"] = estado
    else:
        estado = ""

    cliente_id = entero(params.get("cliente"))
    if cliente_id is not None:
        activos["cliente"] = cliente_id

    opciones = opciones_filtros(usuario)

    if len(q) < MINIMO_CARACTERES:
        duracion = time.perf_counter() - t0
        return {
            "q": q,
            "busqueda_activa": False,
            "minimo_caracteres": MINIMO_CARACTERES,
            "limite": limite,
            "filtros_activos": activos,
            "n_filtros": len(activos),
            "opciones": opciones,
            "entregables": [],
            "entregables_total": 0,
            "contratos": [],
            "clientes": [],
            "adjuntos": [],
            "repositorio": [],
            "total_resultados": 0,
            "tiempo_segundos": duracion,
            "tiempo_texto": f"{duracion:.2f}".replace(".", ","),
        }

    # 1. Entregables
    ent_qs = entregables_visibles(usuario)
    if cliente_id is not None:
        ent_qs = ent_qs.filter(contrato__cliente_id=cliente_id)
    if desde is not None:
        ent_qs = ent_qs.filter(plazo__gte=desde)
    if hasta is not None:
        ent_qs = ent_qs.filter(plazo__lte=hasta)
    if estado in Entregable.Estado.values:
        ent_qs = ent_qs.filter(estado=estado)
    elif estado == subestado.VALOR:
        ent_qs = ent_qs.filter(subestado.condicion())
    if tipo_doc:
        ent_qs = ent_qs.filter(
            Q(adjuntos__tipo=tipo_doc) | Q(plantilla__documento_formato__tipo_documento=tipo_doc)
        ).distinct()

    ent_qs = ent_qs.filter(
        _condicion_campos(
            ("codigo", "titulo", "id_tdr", "contrato__numero_contrato", "contrato__cliente__nombre"),
            q,
        )
    ).select_related("contrato__cliente", "junior_asignado", "senior_revisor")
    entregables_total = ent_qs.count()
    entregables = list(ent_qs.order_by("plazo", "id")[:limite])

    # 2. Contratos
    con_qs = contratos_visibles_busqueda(usuario)
    if cliente_id is not None:
        con_qs = con_qs.filter(cliente_id=cliente_id)
    if desde is not None:
        con_qs = con_qs.filter(fecha_fin__gte=desde)
    if hasta is not None:
        con_qs = con_qs.filter(fecha_inicio__lte=hasta)
    if estado:
        if estado in Entregable.Estado.values:
            con_qs = con_qs.filter(entregables__estado=estado).distinct()
        elif estado == subestado.VALOR:
            con_qs = con_qs.filter(entregables__in=entregables_visibles(usuario).filter(subestado.condicion())).distinct()

    con_qs = con_qs.filter(
        _condicion_campos(("numero_contrato", "descripcion", "cliente__nombre"), q)
    ).select_related("cliente", "linea_servicio")
    contratos = list(con_qs.order_by("numero_contrato")[:limite])

    # 3. Clientes
    cli_qs = clientes_visibles_busqueda(usuario)
    if cliente_id is not None:
        cli_qs = cli_qs.filter(pk=cliente_id)
    if estado:
        if estado in Entregable.Estado.values:
            cli_qs = cli_qs.filter(contratos__entregables__estado=estado).distinct()
        elif estado == subestado.VALOR:
            cli_qs = cli_qs.filter(
                contratos__entregables__in=entregables_visibles(usuario).filter(subestado.condicion())
            ).distinct()

    cli_qs = cli_qs.filter(_condicion_campos(("nombre",), q))
    clientes = list(cli_qs.order_by("nombre")[:limite])

    # 4. Adjuntos
    ent_vis_base = entregables_visibles(usuario)
    if cliente_id is not None:
        ent_vis_base = ent_vis_base.filter(contrato__cliente_id=cliente_id)
    if desde is not None:
        ent_vis_base = ent_vis_base.filter(plazo__gte=desde)
    if hasta is not None:
        ent_vis_base = ent_vis_base.filter(plazo__lte=hasta)
    if estado in Entregable.Estado.values:
        ent_vis_base = ent_vis_base.filter(estado=estado)
    elif estado == subestado.VALOR:
        ent_vis_base = ent_vis_base.filter(subestado.condicion())

    adj_qs = Adjunto.objects.filter(entregable__in=ent_vis_base)
    if tipo_doc:
        adj_qs = adj_qs.filter(tipo=tipo_doc)
    adj_qs = adj_qs.filter(
        _condicion_campos(("nombre_original", "comentario"), q)
    ).select_related("entregable__contrato__cliente")
    adjuntos = list(adj_qs.order_by("-subido_en", "-id")[:limite])

    # 5. Repositorio
    rep_qs = documentos_visibles(usuario)
    if cliente_id is not None:
        rep_qs = rep_qs.filter(cliente_id=cliente_id)
    if tipo_doc:
        rep_qs = rep_qs.filter(tipo_documento=tipo_doc)
    if desde is not None:
        rep_qs = rep_qs.filter(creado_en__date__gte=desde)
    if hasta is not None:
        rep_qs = rep_qs.filter(creado_en__date__lte=hasta)
    if estado:
        # Los documentos del repositorio no tienen estado de ejecución de entregable.
        rep_qs = rep_qs.none()

    rep_qs = rep_qs.filter(_condicion_campos(("titulo",), q)).select_related(
        "cliente", "linea_servicio"
    ).prefetch_related(
        Prefetch("versiones", queryset=VersionDocumento.objects.filter(vigente=True))
    )
    repositorio = list(rep_qs.order_by("titulo", "-id")[:limite])

    total_resultados = len(entregables) + len(contratos) + len(clientes) + len(adjuntos) + len(repositorio)
    duracion = time.perf_counter() - t0
    return {
        "q": q,
        "busqueda_activa": True,
        "minimo_caracteres": MINIMO_CARACTERES,
        "limite": limite,
        "filtros_activos": activos,
        "n_filtros": len(activos),
        "opciones": opciones,
        "entregables": entregables,
        "entregables_total": entregables_total,
        "contratos": contratos,
        "clientes": clientes,
        "adjuntos": adjuntos,
        "repositorio": repositorio,
        "total_resultados": total_resultados,
        "tiempo_segundos": duracion,
        "tiempo_texto": f"{duracion:.2f}".replace(".", ","),
    }
