"""Reglas de las etiquetas (SDD del Sprint 3, §7.2 y §8). Las vistas solo llaman a estas funciones."""
from collections import defaultdict

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from apps.entregables.visibilidad import es_senior_del_entregable

from .models import Etiqueta


# ------------------------------------------------------------------ permisos

def puede_crear(usuario):
    """Senior, gerente y admin crean y editan etiquetas; el junior no."""
    return bool(usuario.is_authenticated and (usuario.es_senior or usuario.es_gerente_o_admin))


def puede_dar_de_baja(usuario):
    return bool(usuario.is_authenticated and usuario.es_gerente_o_admin)


def puede_asignar(usuario, entregable):
    """Gerente y admin, o el senior del entregable (responsable del contrato o revisor)."""
    return bool(usuario.is_authenticated and es_senior_del_entregable(usuario, entregable))


def puede_asignar_a_contrato(usuario):
    return puede_dar_de_baja(usuario)


def exigir(permitido):
    if not permitido:
        raise PermissionDenied("No tiene permiso para esa acción con las etiquetas.")


# ------------------------------------------------------------------ crear y editar

def nombre_normalizado(nombre):
    return " ".join((nombre or "").split())


def nombre_en_uso(nombre, excepto_pk=None):
    """True si ya existe una etiqueta con ese nombre (sin distinguir mayúsculas ni tildes de mayúscula).

    Se compara en Python: `Lower` de SQLite solo entiende ASCII y el catálogo es pequeño.
    """
    existentes = Etiqueta.objects.exclude(pk=excepto_pk).values_list("nombre", flat=True)
    return any(otro.casefold() == nombre.casefold() for otro in existentes)


def crear(usuario, nombre, color):
    exigir(puede_crear(usuario))
    nombre = nombre_normalizado(nombre)
    if not nombre:
        raise ValidationError("Falta el nombre de la etiqueta.")
    if color not in Etiqueta.Color.values:
        raise ValidationError("Elija uno de los colores de la lista.")
    if nombre_en_uso(nombre):
        raise ValidationError("Ya existe una etiqueta con ese nombre.")
    return Etiqueta.objects.create(nombre=nombre, color=color, creada_por=usuario)


def cambiar_baja(usuario, etiqueta, activa):
    exigir(puede_dar_de_baja(usuario))
    etiqueta.activa = activa
    etiqueta.save(update_fields=["activa"])
    return etiqueta


# ------------------------------------------------------------------ asignación

def ofrecidas_para(entregable=None):
    """Etiquetas que se pueden elegir: las activas y, en un entregable existente, las que ya tiene (aunque estén de baja)."""
    qs = Etiqueta.objects.filter(activa=True)
    if entregable is not None and entregable.pk:
        qs = Etiqueta.objects.filter(activa=True) | Etiqueta.objects.filter(entregables=entregable)
    return qs.distinct()


def _validar(etiquetas, entregable=None):
    permitidas = {e.pk for e in ofrecidas_para(entregable)}
    for etiqueta in etiquetas:
        if etiqueta.pk not in permitidas:
            raise ValidationError(f"La etiqueta «{etiqueta.nombre}» no está disponible.")


@transaction.atomic
def asignar(usuario, entregable, etiquetas):
    """Deja al entregable con exactamente `etiquetas` como propias (las del contrato no se tocan). Solo quien puede asignar."""
    exigir(puede_asignar(usuario, entregable))
    etiquetas = list(etiquetas)
    _validar(etiquetas, entregable)
    entregable.etiquetas_asignadas.set(etiquetas)
    return etiquetas


def asignar_en_creacion(entregable, etiquetas):
    """Al crear el entregable: quien lo crea ya pasó por las reglas del formulario (solo etiquetas ofrecidas)."""
    etiquetas = list(etiquetas)
    _validar(etiquetas)
    if etiquetas:
        entregable.etiquetas_asignadas.set(etiquetas)
    return etiquetas


def asignar_a_contrato(usuario, contrato, etiquetas):
    exigir(puede_asignar_a_contrato(usuario))
    contrato.etiquetas_asignadas.set(list(etiquetas))


# ------------------------------------------------------------------ lectura

def etiquetas_de(entregable):
    """Las del entregable más las de su contrato, sin repetir, por nombre."""
    propias = Etiqueta.objects.filter(entregables=entregable)
    del_contrato = Etiqueta.objects.filter(contratos=entregable.contrato_id)
    vistas, salida = set(), []
    for etiqueta in (propias | del_contrato).distinct():
        if etiqueta.pk not in vistas:
            vistas.add(etiqueta.pk)
            salida.append(etiqueta)
    return salida


def enriquecer(entregables, usuario=None):
    """Deja `e.etiquetas` (lista) en cada tarjeta o fila con dos consultas por lote, no una por entregable."""
    entregables = list(entregables) if not isinstance(entregables, list) else entregables
    ids = [e.pk for e in entregables]
    contratos = {e.contrato_id for e in entregables}
    por_entregable, por_contrato = defaultdict(dict), defaultdict(dict)
    if ids:
        for fila in Etiqueta.entregables.through.objects.filter(entregable_id__in=ids).select_related("etiqueta"):
            por_entregable[fila.entregable_id][fila.etiqueta_id] = fila.etiqueta
        for fila in Etiqueta.contratos.through.objects.filter(contrato_id__in=contratos).select_related("etiqueta"):
            por_contrato[fila.contrato_id][fila.etiqueta_id] = fila.etiqueta
    for e in entregables:
        juntas = {**por_contrato.get(e.contrato_id, {}), **por_entregable.get(e.pk, {})}
        e.etiquetas = sorted(juntas.values(), key=lambda t: (t.nombre.casefold(), t.pk))
    return entregables


def condicion(etiqueta_id):
    """Condición sobre Entregable: tiene esa etiqueta, propia o de su contrato (subconsultas: sin filas repetidas)."""
    return (
        Q(pk__in=Etiqueta.entregables.through.objects.filter(etiqueta_id=etiqueta_id).values("entregable_id"))
        | Q(contrato_id__in=Etiqueta.contratos.through.objects.filter(etiqueta_id=etiqueta_id).values("contrato_id"))
    )


def opciones_de_filtro(visibles):
    """Etiquetas del desplegable «Etiqueta»: solo las que aparecen en lo que el usuario ya puede ver (`visibles`: queryset de pk)."""
    return Etiqueta.objects.filter(
        Q(pk__in=Etiqueta.entregables.through.objects.filter(entregable_id__in=visibles).values("etiqueta_id"))
        | Q(pk__in=Etiqueta.contratos.through.objects.filter(contrato__entregables__in=visibles).values("etiqueta_id"))
    )


def etiqueta_de_linea(contrato):
    """La etiqueta de la línea de servicio del contrato (o None)."""
    if not contrato or not contrato.linea_servicio_id:
        return None
    return Etiqueta.objects.filter(linea_servicio_id=contrato.linea_servicio_id, activa=True).first()
