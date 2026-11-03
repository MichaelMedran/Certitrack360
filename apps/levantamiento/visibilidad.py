"""Visibilidad y permisos de las fichas de levantamiento (SDD del Sprint 2, §7.5 y §8)."""
from django.db.models import Q

from apps.clientes.models import Contrato

from .models import FichaLevantamiento


def contratos_para_ficha(usuario):
    """Contratos vigentes (con cliente activo) en los que el usuario puede redactar una ficha."""
    qs = Contrato.objects.select_related("cliente", "senior_responsable", "linea_servicio").filter(
        activo=True, cliente__activo=True
    )
    if usuario.es_gerente_o_admin:
        return qs
    if usuario.es_senior:
        return qs.filter(senior_responsable=usuario)
    return qs.filter(juniors=usuario).distinct()


def fichas_visibles(usuario):
    """Fichas que el usuario puede ver según su rol (404 fuera de este queryset)."""
    qs = FichaLevantamiento.objects.all()
    if usuario.es_gerente_o_admin:
        return qs
    if usuario.es_senior:
        return qs.filter(Q(contrato__senior_responsable=usuario) | Q(responsable=usuario)).distinct()
    return qs.filter(contrato__juniors=usuario).distinct()


def puede_redactar_en_contrato(usuario, contrato):
    """Si el usuario puede redactar o editar una ficha en este contrato."""
    if not contrato.activo or not contrato.cliente.activo:
        return False
    if usuario.es_gerente_o_admin:
        return True
    if usuario.es_senior:
        return contrato.senior_responsable_id == usuario.pk
    return contrato.juniors.filter(pk=usuario.pk).exists()


def puede_editar_borrador(usuario, ficha):
    """Quién puede editar una ficha en borrador o pedir confirmación: junior asignado al contrato,
    senior del contrato (o responsable de la ficha), gerente y admin."""
    if ficha.confirmada:
        return False
    if usuario.es_gerente_o_admin:
        return True
    if usuario.es_senior:
        return ficha.contrato.senior_responsable_id == usuario.pk or ficha.responsable_id == usuario.pk
    return ficha.contrato.juniors.filter(pk=usuario.pk).exists()


def puede_confirmar(usuario, ficha):
    """Solo el senior responsable del contrato, el gerente o el admin pueden confirmar la ficha y generar entregables (C7, §8)."""
    if usuario.es_gerente_o_admin:
        return True
    return usuario.es_senior and ficha.contrato.senior_responsable_id == usuario.pk


def puede_actualizar_documental(usuario, ficha):
    """En una ficha confirmada, quién puede actualizar el estado documental actual (HU-06)."""
    if not ficha.confirmada:
        return False
    if usuario.es_gerente_o_admin:
        return True
    if usuario.es_senior:
        return ficha.contrato.senior_responsable_id == usuario.pk or ficha.responsable_id == usuario.pk
    return ficha.contrato.juniors.filter(pk=usuario.pk).exists()
