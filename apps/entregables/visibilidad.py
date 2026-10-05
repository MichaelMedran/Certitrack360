"""Filtros de visibilidad: se aplican en el queryset base de toda vista y del calendario."""
from django.db.models import Q

from .models import Entregable


def entregables_visibles(usuario):
    qs = Entregable.objects.all()
    if usuario.es_gerente_o_admin:
        return qs
    if usuario.es_senior:
        return qs.filter(
            Q(contrato__senior_responsable=usuario) | Q(senior_revisor=usuario) | Q(junior_asignado=usuario)
        ).distinct()
    return qs.filter(junior_asignado=usuario)


def es_senior_del_entregable(usuario, entregable):
    """Gerente/Admin, o el senior responsable del contrato / revisor del entregable."""
    if usuario.es_gerente_o_admin:
        return True
    return usuario.es_senior and usuario.pk in (
        entregable.senior_revisor_id, entregable.contrato.senior_responsable_id
    )
