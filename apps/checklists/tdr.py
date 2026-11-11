"""Checklist por TDR (SDD del Sprint 3, RF-44 y §7.5; HU-25).

Un ítem por requisito, documento o formato que exige la ficha de levantamiento del contrato, más los que se agreguen a
mano. No bloquea: enviar a Revisión senior con obligatorios pendientes pide una confirmación (`extensiones.Advertencia`)
y, si se confirma, queda en el historial.
"""
import re

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from apps.entregables import adjuntos
from apps.entregables.extensiones import Advertencia
from apps.entregables.models import Adjunto, Entregable
from apps.entregables.visibilidad import entregables_visibles, es_responsable_activo

from .models import ItemChecklistTDR

E = Entregable.Estado
T = ItemChecklistTDR.Tipo
CLAVE_ADVERTENCIA = "checklist_tdr"
TEXTO_MAX = ItemChecklistTDR._meta.get_field("texto").max_length
_VINETA = re.compile(r"^\s*(?:[-•*·–—]+|\d+[.)]|[a-zA-Z][.)])\s+")


def enlace(entregable):
    return reverse("entregable_detalle", args=[entregable.pk]) + "#checklist-tdr"


def puede_gestionar(usuario, entregable):
    """Marcan, agregan y generan: los responsables activos (junior asignado, apoyos y seniors del entregable; gerente y
    admin). Un entregado ya no se modifica."""
    return entregable.estado != E.HECHO and es_responsable_activo(usuario, entregable)


def _exigir(usuario, entregable):
    if not es_responsable_activo(usuario, entregable):
        raise PermissionDenied("Solo los responsables del entregable gestionan su checklist.")
    if entregable.estado == E.HECHO:
        raise ValidationError(f"El checklist de un entregable «{E.HECHO.label}» ya no se modifica.")


def _lineas(texto, separadores=r"[\r\n]+"):
    """Líneas no vacías de un texto, sin viñetas ni numeración, sin repetir y acotadas al largo del campo."""
    salida = []
    for linea in re.split(separadores, texto or ""):
        linea = _VINETA.sub("", linea).strip().rstrip(".;,").strip()
        if linea and linea.lower() not in (s.lower() for s in salida):
            salida.append(linea[:TEXTO_MAX])
    return salida


def items_de_ficha(ficha):
    """[(tipo, texto, obligatorio)] que exige la ficha: requisitos y documentos (obligatorios) y formatos."""
    propuestos = [(T.REQUISITO, t, True) for t in _lineas(ficha.requerimientos)]
    propuestos += [(T.DOCUMENTO, t, True) for t in _lineas(ficha.documentos_disponibles)]
    propuestos += [(T.DOCUMENTO, t, True) for t in _lineas(ficha.documentos_faltantes)]
    formatos = _lineas(ficha.formatos, r"[\r\n;,]+") + _lineas(ficha.formato_esperado, r"[\r\n;]+")
    propuestos += [(T.FORMATO, t, False) for t in formatos]
    vistos, salida = set(), []
    for tipo, texto, obligatorio in propuestos:
        clave = (tipo, texto.lower())
        if clave not in vistos:
            vistos.add(clave)
            salida.append((tipo, texto, obligatorio))
    return salida


def ficha_para(entregable):
    """La ficha confirmada de la que sale el checklist: la que generó el entregable; si no, la del mismo ID-TDR; si no,
    la última confirmada del contrato. None si el contrato no tiene ninguna."""
    from apps.levantamiento.models import FichaLevantamiento

    confirmadas = FichaLevantamiento.objects.filter(
        contrato_id=entregable.contrato_id, estado=FichaLevantamiento.Estado.CONFIRMADA
    )
    origen = confirmadas.filter(items__entregables_generados=entregable).first()
    if origen:
        return origen
    if entregable.id_tdr:
        misma = confirmadas.filter(id_tdr__iexact=entregable.id_tdr).order_by("-confirmada_en", "-id").first()
        if misma:
            return misma
    return confirmadas.order_by("-confirmada_en", "-id").first()


def _crear_desde_ficha(entregable, ficha, usuario):
    """Crea los ítems de la ficha que el entregable todavía no tiene (no duplica). Devuelve los creados."""
    existentes = {(i.tipo, i.texto.lower()) for i in entregable.checklist_tdr.all()}
    orden = entregable.checklist_tdr.count()
    nuevos = []
    for tipo, texto, obligatorio in items_de_ficha(ficha):
        if (tipo, texto.lower()) in existentes:
            continue
        orden += 1
        nuevos.append(ItemChecklistTDR(
            entregable=entregable, texto=texto, tipo=tipo, obligatorio=obligatorio, orden=orden,
            origen=ItemChecklistTDR.Origen.FICHA, creado_por=usuario,
        ))
    return ItemChecklistTDR.objects.bulk_create(nuevos)


def generar(entregable, usuario):
    """«Generar desde el TDR»: crea el checklist a partir de la ficha confirmada del contrato. Devuelve los ítems creados."""
    _exigir(usuario, entregable)
    ficha = ficha_para(entregable)
    if ficha is None:
        raise ValidationError("El contrato no tiene una ficha de levantamiento confirmada: agregue los ítems a mano.")
    with transaction.atomic():
        creados = _crear_desde_ficha(entregable, ficha, usuario)
        if creados:
            adjuntos.registrar_en_historial(
                entregable, usuario, f"Generó el checklist por TDR desde la ficha {ficha.id_tdr} ({len(creados)} ítems)"[:255]
            )
    return creados


def generar_al_confirmar_ficha(entregable, ficha, usuario):
    """Al confirmar una ficha, cada entregable generado recibe su checklist (sin permisos: lo hace la confirmación)."""
    return _crear_desde_ficha(entregable, ficha, usuario)


def agregar(entregable, usuario, texto, tipo=T.REQUISITO, obligatorio=False):
    _exigir(usuario, entregable)
    texto = (texto or "").strip()
    if not texto:
        raise ValidationError("Escriba el requisito, documento o formato que quiere agregar.")
    if len(texto) > TEXTO_MAX:
        raise ValidationError(f"El texto del ítem no puede pasar de {TEXTO_MAX} caracteres.")
    if tipo not in T.values:
        raise ValidationError("Elija si el ítem es un requisito, un documento o un formato.")
    if entregable.checklist_tdr.filter(tipo=tipo, texto__iexact=texto).exists():
        raise ValidationError("Ese ítem ya está en el checklist.")
    return ItemChecklistTDR.objects.create(
        entregable=entregable, texto=texto, tipo=tipo, obligatorio=bool(obligatorio),
        orden=entregable.checklist_tdr.count() + 1, origen=ItemChecklistTDR.Origen.MANUAL, creado_por=usuario,
    )


def marcar(item, usuario, estado, adjunto=None):
    """Cambia el estado de un ítem (Pendiente, En revisión o Cumplido) y, si se indica, el documento que lo sustenta.
    Guarda quién lo marcó y cuándo."""
    entregable = item.entregable
    _exigir(usuario, entregable)
    if estado not in ItemChecklistTDR.Estado.values:
        raise ValidationError("Elija un estado válido para el ítem.")
    sustento = None
    if adjunto not in (None, ""):
        adjunto_id = adjunto.pk if isinstance(adjunto, Adjunto) else adjunto
        try:
            sustento = Adjunto.objects.get(pk=int(adjunto_id), entregable_id=entregable.pk)
        except (TypeError, ValueError, OverflowError, Adjunto.DoesNotExist):
            raise ValidationError("El documento de sustento debe ser un adjunto de este mismo entregable.")
    item.estado, item.adjunto = estado, sustento
    item.marcado_por, item.marcado_en = usuario, timezone.now()
    item.save(update_fields=["estado", "adjunto", "marcado_por", "marcado_en"])
    return item


def resumen(entregable, items=None):
    """Ítems, total, cumplidos, % de cumplimiento (cumplidos ÷ total) y obligatorios que siguen sin cumplir."""
    if items is None:
        items = list(entregable.checklist_tdr.select_related("marcado_por", "adjunto"))
    total = len(items)
    cumplidos = sum(1 for i in items if i.cumplido)
    return {
        "items": items, "total": total, "cumplidos": cumplidos,
        "porcentaje": round(100 * cumplidos / total) if total else 0,
        "obligatorios_pendientes": [i for i in items if i.obligatorio and not i.cumplido],
    }


def obligatorios_pendientes(entregable):
    return entregable.checklist_tdr.filter(obligatorio=True).exclude(estado=ItemChecklistTDR.Estado.CUMPLIDO)


def _plural(n):
    return f"{n} ítem obligatorio" if n == 1 else f"{n} ítems obligatorios"


# ------------------------------------------------------------------ extensiones de la máquina de estados (§5.1)

def condicion(entregable, nuevo_estado, usuario, opciones):
    """Antes de enviar a Revisión senior: avisa si quedan obligatorios pendientes (HU-25 criterio 4). No bloquea."""
    if nuevo_estado != E.VERIFICACION_SENIOR:
        return None
    pendientes = list(obligatorios_pendientes(entregable)[:4])
    if not pendientes:
        return None
    n = obligatorios_pendientes(entregable).count()
    nombres = ", ".join(f"«{i.texto}»" for i in pendientes[:3]) + ("…" if n > 3 else "")
    return Advertencia(
        CLAVE_ADVERTENCIA,
        f"El checklist por TDR tiene {_plural(n)} sin cumplir ({nombres}). "
        f"¿Enviar a «{E.VERIFICACION_SENIOR.label}» de todos modos?",
    )


def al_mover(entregable, anterior, nuevo, usuario, opciones):
    """Si se envió a revisión confirmando el aviso, queda en el historial cuántos obligatorios seguían pendientes."""
    if nuevo != E.VERIFICACION_SENIOR or CLAVE_ADVERTENCIA not in (opciones.get("confirmadas") or ()):
        return
    n = obligatorios_pendientes(entregable).count()
    if n:
        adjuntos.registrar_en_historial(
            entregable, usuario, f"Enviado a revisión con {_plural(n)} del checklist por TDR pendiente{'s' if n != 1 else ''}"
        )


# ------------------------------------------------------------------ detalle y consulta

def seccion(usuario, entregable):
    """Sección «Checklist por TDR» del detalle: se muestra si hay ítems o si el usuario puede crearlos."""
    datos = resumen(entregable)
    puede = puede_gestionar(usuario, entregable)
    if not datos["total"] and not puede:
        return None
    return {
        "plantilla": "checklists/_tdr.html", "orden": 20,
        "contexto": {
            **datos, "puede": puede, "tipos": T.choices, "estados": ItemChecklistTDR.Estado.choices,
            "hay_ficha": puede and ficha_para(entregable) is not None,
            "adjuntos": list(entregable.adjuntos.order_by("tipo", "-version")) if puede and datos["total"] else [],
        },
    }


def entregables_con_checklist(usuario):
    """Entregables visibles que tienen checklist, con sus cuentas, para la pestaña «Checklists»."""
    C = ItemChecklistTDR.Estado.CUMPLIDO
    return (
        entregables_visibles(usuario)
        .annotate(
            n_items=Count("checklist_tdr", distinct=True),
            n_cumplidos=Count("checklist_tdr", filter=Q(checklist_tdr__estado=C), distinct=True),
            n_obligatorios_pendientes=Count(
                "checklist_tdr", filter=Q(checklist_tdr__obligatorio=True) & ~Q(checklist_tdr__estado=C), distinct=True
            ),
        )
        .filter(n_items__gt=0)
        .select_related("contrato__cliente", "junior_asignado")
    )
