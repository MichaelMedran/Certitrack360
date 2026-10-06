"""Datos de navegación para la barra superior: qué sección está activa."""

# nombre de la URL -> sección de la barra
SECCIONES = {
    "inicio": "inicio",
    "tablero": "tablero",
    "calendario": "calendario",
    "entregables": "entregables", "entregable_nuevo": "entregables", "entregable_detalle": "entregables",
    "asistente": "asistente",
    "consolidado": "consolidado",
    "gestion": "gestion", "adm_lista": "gestion", "adm_nuevo": "gestion", "adm_editar": "gestion",
    "notificaciones": "avisos",
}


def navegacion(request):
    coincidencia = getattr(request, "resolver_match", None)
    return {"seccion": SECCIONES.get(coincidencia.url_name) if coincidencia else None}
