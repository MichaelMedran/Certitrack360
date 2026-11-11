"""Checklist de control de calidad (SDD del Sprint 3, RF-45 y §7.6; HU-26).

El senior lo aplica cuando el entregable está en Revisión senior. Solo se aprueba con una revisión conforme del ciclo de
revisión actual; un ítem no conforme registra su observación y, como en RF-26, devuelve el entregable a En proceso.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.urls import reverse

from apps.clientes.models import Cliente
from apps.entregables import observaciones as obs_servicio
from apps.entregables.models import Entregable, HistorialEstado, TipoError
from apps.entregables.visibilidad import es_senior_del_entregable

from .models import ItemCalidad, RespuestaCalidad, RevisionCalidad

E = Entregable.Estado
R = RevisionCalidad.Resultado
C = ItemCalidad.Categoria

#: Los cuatro ítems generales mínimos de HU-26 (criterio 1). La migración 0002 los crea.
ITEMS_INICIALES = (
    (C.INFORMACION_COMPLETA, "La información está completa: no faltan datos, secciones ni anexos exigidos."),
    (C.CONSISTENCIA, "Los datos son consistentes entre sí y con las fuentes (cifras, nombres y totales coinciden)."),
    (C.FECHAS_VIGENCIA, "Las fechas son correctas y los documentos adjuntos están vigentes."),
    (C.FORMATO, "El entregable respeta el formato exigido por el cliente."),
)

#: Tipo de error de la observación que genera un ítem no conforme, según su categoría.
TIPO_ERROR = {
    C.INFORMACION_COMPLETA: TipoError.DATO_FALTANTE, C.CONSISTENCIA: TipoError.CONTENIDO,
    C.FECHAS_VIGENCIA: TipoError.CONTENIDO, C.FORMATO: TipoError.FORMATO, C.OTRO: TipoError.OTRO,
}

MOTIVO_SIN_REVISION = (
    f"No se puede aprobar: falta el checklist de control de calidad de esta revisión con todos los ítems obligatorios en "
    f"«{R.CONFORME.label}». Complételo en la sección «Checklist de calidad»."
)


def enlace(entregable):
    return reverse("entregable_detalle", args=[entregable.pk]) + "#checklist-calidad"


# ------------------------------------------------------------------ configuración por cliente

def clientes_configurables(usuario):
    """Clientes cuyos ítems puede configurar: todos (gerente y admin) o los de sus contratos (senior)."""
    if usuario.es_gerente_o_admin:
        return Cliente.objects.all()
    if usuario.es_senior:
        return Cliente.objects.filter(contratos__senior_responsable=usuario).distinct()
    return Cliente.objects.none()


def puede_configurar(usuario, cliente=None):
    """Los ítems generales (sin cliente) solo los edita gerente o admin; los de un cliente, también sus seniors."""
    if usuario.es_gerente_o_admin:
        return True
    return cliente is not None and clientes_configurables(usuario).filter(pk=cliente.pk).exists()


def puede_ver_configuracion(usuario):
    return usuario.es_gerente_o_admin or usuario.es_senior


def guardar_item(usuario, item=None, *, cliente=None, texto="", categoria=C.OTRO, obligatorio=True, activo=True):
    """Crea o edita un ítem. Editar no cambia el cliente del ítem. Lanza PermissionDenied o ValidationError."""
    if item is not None:
        cliente = item.cliente
    if not puede_configurar(usuario, cliente):
        raise PermissionDenied("Solo el gerente o el admin editan los ítems generales; los seniors, los de sus clientes.")
    texto = (texto or "").strip()
    if not texto:
        raise ValidationError("Escriba qué se verifica en el ítem.")
    if len(texto) > ItemCalidad._meta.get_field("texto").max_length:
        raise ValidationError("El texto del ítem es demasiado largo (máximo 300 caracteres).")
    if categoria not in C.values:
        raise ValidationError("Elija una categoría válida.")
    if item is None:
        ultimo = ItemCalidad.objects.filter(cliente=cliente).order_by("-orden").values_list("orden", flat=True).first()
        item = ItemCalidad(cliente=cliente, orden=(ultimo or 0) + 1)
    item.texto, item.categoria, item.obligatorio, item.activo = texto, categoria, bool(obligatorio), bool(activo)
    item.save()
    return item


# ------------------------------------------------------------------ revisión

def items_aplicables(entregable):
    """Ítems activos que aplican al entregable: los generales y, después, los de su cliente."""
    cliente_id = entregable.contrato.cliente_id
    items = list(ItemCalidad.objects.filter(activo=True).filter(Q(cliente__isnull=True) | Q(cliente_id=cliente_id)))
    return sorted(items, key=lambda i: (i.cliente_id is not None, i.orden, i.pk))


def puede_revisar(usuario, entregable):
    return es_senior_del_entregable(usuario, entregable)


def paso_actual(entregable):
    """Registro del historial del último paso a «Revisión senior»: identifica el ciclo de revisión actual. None si el
    entregable llegó a ese estado sin historial (datos antiguos o de prueba)."""
    return (
        HistorialEstado.objects.filter(entregable=entregable, estado_nuevo=E.VERIFICACION_SENIOR)
        .exclude(estado_anterior=E.VERIFICACION_SENIOR).order_by("-fecha", "-id").first()
    )


def revision_vigente(entregable):
    """La última revisión del ciclo actual, o None (las de ciclos anteriores no cuentan)."""
    paso = paso_actual(entregable)
    return entregable.revisiones_calidad.filter(paso=paso).order_by("-id").first()


def registrar(entregable, usuario, respuestas):
    """Registra una revisión de calidad. `respuestas`: {id del ítem: (resultado, observación)} para TODOS los ítems
    aplicables. Devuelve (revisión, devuelto: bool).

    - Un No conforme exige su observación.
    - Resultado CONFORME si todos los ítems obligatorios están conformes; si no, NO_CONFORME.
    - Cada ítem no conforme registra una observación (`observaciones.registrar`): el entregable vuelve a En proceso con
      «Con correcciones pendientes» y se avisa al junior (RF-26).
    """
    if not puede_revisar(usuario, entregable):
        raise PermissionDenied("Solo el senior del entregable, el gerente o el admin registran la revisión de calidad.")
    if entregable.estado != E.VERIFICACION_SENIOR:
        raise ValidationError(
            f"El checklist de calidad se aplica cuando el entregable está en «{E.VERIFICACION_SENIOR.label}»; este está "
            f"«{entregable.get_estado_display()}»."
        )
    items = items_aplicables(entregable)
    if not items:
        raise ValidationError("No hay ítems de calidad configurados para este cliente.")
    filas, errores = [], []
    for item in items:
        resultado, observacion = respuestas.get(item.pk) or respuestas.get(str(item.pk)) or (None, "")
        observacion = (observacion or "").strip()
        if resultado not in R.values:
            errores.append(f"Marque «{item.texto}» como {R.CONFORME.label} o {R.NO_CONFORME.label}.")
        elif resultado == R.NO_CONFORME and not observacion:
            errores.append(f"«{item.texto}» está {R.NO_CONFORME.label.lower()}: registre la observación.")
        else:
            filas.append((item, resultado, observacion if resultado == R.NO_CONFORME else ""))
    if errores:
        raise ValidationError(errores)
    no_conformes = [(i, o) for i, r, o in filas if r == R.NO_CONFORME]
    conforme = not any(i.obligatorio for i, _ in no_conformes)
    with transaction.atomic():
        revision = RevisionCalidad.objects.create(
            entregable=entregable, revisor=usuario, paso=paso_actual(entregable),
            resultado=R.CONFORME if conforme else R.NO_CONFORME,
        )
        RespuestaCalidad.objects.bulk_create([
            RespuestaCalidad(revision=revision, item=item, texto=item.texto, obligatorio=item.obligatorio,
                             resultado=resultado, observacion=observacion)
            for item, resultado, observacion in filas
        ])
        devuelto = False
        if no_conformes:
            _, devuelto = obs_servicio.registrar(entregable, usuario, [
                {"tipo_error": TIPO_ERROR[item.categoria], "descripcion": f"Control de calidad · {item.texto} — {observacion}"}
                for item, observacion in no_conformes
            ])
    return revision, devuelto


def registrar_conforme(entregable, usuario):
    """Registra una revisión con todos los ítems aplicables en Conforme. La usan el ayudante de pruebas `aprobar` y el
    `seed_demo`. Si no corresponde (otro estado, sin ítems o sin permiso) no hace nada y devuelve None: quien llama sigue
    con `mover`, que dará el motivo."""
    if entregable.estado != E.VERIFICACION_SENIOR or not puede_revisar(usuario, entregable):
        return None
    items = items_aplicables(entregable)
    if not items:
        return None
    revision, _ = registrar(entregable, usuario, {i.pk: (R.CONFORME, "") for i in items})
    return revision


# ------------------------------------------------------------------ extensiones (§5.1)

def condicion(entregable, nuevo_estado, usuario, opciones):
    """Para aprobar (Revisión senior → Aprobado) hace falta la revisión conforme del ciclo actual (HU-26 criterio 4)."""
    if nuevo_estado != E.LISTO_PARA_ENTREGA or entregable.estado != E.VERIFICACION_SENIOR:
        return None
    if not items_aplicables(entregable):
        return None
    revision = revision_vigente(entregable)
    return None if revision is not None and revision.conforme else MOTIVO_SIN_REVISION


def seccion(usuario, entregable):
    """Sección «Checklist de calidad» del detalle: el formulario en Revisión senior y el historial de revisiones."""
    revisiones = list(entregable.revisiones_calidad.select_related("revisor").prefetch_related("respuestas"))
    en_revision = entregable.estado == E.VERIFICACION_SENIOR
    if not en_revision and not revisiones:
        return None
    items = items_aplicables(entregable) if en_revision else []
    vigente = revision_vigente(entregable) if en_revision else None
    return {
        "plantilla": "checklists/_calidad.html", "orden": 30,
        "contexto": {
            "en_revision": en_revision, "items": items, "revisiones": revisiones, "vigente": vigente,
            "puede_revisar": en_revision and bool(items) and puede_revisar(usuario, entregable),
            "puede_configurar": puede_configurar(usuario, entregable.contrato.cliente),
            "CONFORME": R.CONFORME, "NO_CONFORME": R.NO_CONFORME,
        },
    }
