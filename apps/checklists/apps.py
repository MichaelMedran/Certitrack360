from django.apps import AppConfig


class ChecklistsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.checklists"
    verbose_name = "Checklists"

    def ready(self):
        from django.db.models.signals import m2m_changed

        from apps.entregables import extensiones
        from apps.levantamiento.models import ItemFicha

        from . import calidad, tdr

        # Checklist por TDR (RF-44): aviso con confirmación al enviar a revisión, sección del detalle y generación
        # automática para los entregables que nacen de una ficha de levantamiento.
        extensiones.registrar_condicion(tdr.condicion)
        extensiones.registrar_al_mover(tdr.al_mover)
        extensiones.registrar_seccion(tdr.seccion)
        m2m_changed.connect(
            _checklist_de_entregables_generados, sender=ItemFicha.entregables_generados.through,
            dispatch_uid="checklists.generar_desde_ficha",
        )
        # Checklist de calidad (RF-45): condición para aprobar y sección del detalle.
        extensiones.registrar_condicion(calidad.condicion)
        extensiones.registrar_seccion(calidad.seccion)


def _checklist_de_entregables_generados(sender, instance, action, reverse, pk_set, **kwargs):
    """Al confirmar una ficha, cada entregable generado por un ítem recibe el checklist de esa ficha (§7.5)."""
    if action != "post_add" or reverse or not pk_set:
        return
    from apps.entregables.models import Entregable

    from . import tdr

    for entregable in Entregable.objects.filter(pk__in=pk_set).select_related("creado_por"):
        tdr.generar_al_confirmar_ficha(entregable, instance.ficha, entregable.creado_por)
