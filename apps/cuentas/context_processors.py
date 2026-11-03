"""Datos de navegación para la barra superior: qué sección está activa."""

# nombre de la URL -> sección de la barra
SECCIONES = {
    "inicio": "inicio",
    "tablero": "tablero",
    "calendario": "calendario",
    "entregables": "entregables", "entregable_nuevo": "entregables", "entregable_detalle": "entregables",
    "entregable_responsables": "entregables",
    "entregable_tiempo": "entregables", "tiempos": "entregables",  # pestaña «Tiempos» y registro por etapa (RF-32)
    "observaciones": "entregables",  # pestaña «Observaciones» de Entregables (SDD del Sprint 2, §9.2)
    "entregas": "entregables", "entregable_entregar": "entregables",  # pestaña «Entregas» y formulario de entrega (RF-29)
    "indicadores": "indicadores",
    "repositorio": "repositorio", "repositorio_nuevo": "repositorio", "repositorio_documento": "repositorio",
    "procedimientos": "repositorio",
    "asistente": "asistente",
    "consolidado": "consolidado",
    "gestion": "gestion", "adm_lista": "gestion", "adm_nuevo": "gestion", "adm_editar": "gestion",
    "lineas_servicio": "gestion", "personal": "gestion",
    "fichas": "gestion", "ficha_nueva": "gestion", "ficha_detalle": "gestion",
    "ficha_vista_previa": "gestion", "ficha_confirmar": "gestion",
    "notificaciones": "avisos",
}


def navegacion(request):
    coincidencia = getattr(request, "resolver_match", None)
    return {"seccion": SECCIONES.get(coincidencia.url_name) if coincidencia else None}
