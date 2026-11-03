"""Filtros de visibilidad: se aplican en el queryset base de toda vista y del calendario."""
from django.db.models import Q

from .models import Entregable, ResponsableApoyo


def entregables_visibles(usuario):
    qs = Entregable.objects.all()
    if usuario.es_gerente_o_admin:
        return qs
    apoyo = Q(responsables_apoyo__usuario=usuario, responsables_apoyo__activo=True)
    if usuario.es_senior:
        return qs.filter(
            Q(contrato__senior_responsable=usuario) | Q(senior_revisor=usuario) | Q(junior_asignado=usuario) | apoyo
        ).distinct()
    return qs.filter(Q(junior_asignado=usuario) | apoyo).distinct()


def es_senior_del_entregable(usuario, entregable):
    """Gerente/Admin, o el senior responsable del contrato / revisor del entregable."""
    if usuario.es_gerente_o_admin:
        return True
    return usuario.es_senior and usuario.pk in (
        entregable.senior_revisor_id, entregable.contrato.senior_responsable_id
    )


def es_apoyo_activo(usuario, entregable):
    """True si la persona figura como responsable de apoyo activo en el entregable (RF-31)."""
    if not getattr(usuario, "pk", None) or not getattr(entregable, "pk", None):
        return False
    return ResponsableApoyo.objects.filter(entregable_id=entregable.pk, usuario_id=usuario.pk, activo=True).exists()


def es_elaborador_del_entregable(usuario, entregable):
    """Junior asignado o responsable de apoyo activo: puede elaborar, subir adjuntos en estados iniciales y avanzar
    hasta Revisión senior, pero no aprobar ni devolver salvo que sea senior del entregable (§7.1 y §7.6)."""
    return usuario.pk == entregable.junior_asignado_id or es_apoyo_activo(usuario, entregable)


def es_responsable_activo(usuario, entregable):
    """Cualquier responsable activo del entregable (junior asignado, apoyo activo o senior del entregable)."""
    return es_elaborador_del_entregable(usuario, entregable) or es_senior_del_entregable(usuario, entregable)
