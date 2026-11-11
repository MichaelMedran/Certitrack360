"""Alertas urgentes sin leer del usuario, para la franja «URGENTE» de todas las pantallas (RF-43)."""


def urgentes(request):
    """{"alertas_urgentes": [...]}: las alertas abiertas que el usuario recibió y todavía no confirmó como leídas.

    Cada alerta lleva `ver_entregable` (bool): quien está de guardia sin ser responsable del entregable no lo ve (404), así que
    la franja le ofrece confirmar y aceptar sin enlace.
    """
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {"alertas_urgentes": []}
    from apps.entregables.visibilidad import entregables_visibles

    from . import servicios

    alertas = servicios.pendientes_de_lectura(usuario)
    if alertas:
        visibles = set(
            entregables_visibles(usuario).filter(pk__in=[a.entregable_id for a in alertas]).values_list("pk", flat=True)
        )
        for a in alertas:
            a.ver_entregable = a.entregable_id in visibles
    return {"alertas_urgentes": alertas}
