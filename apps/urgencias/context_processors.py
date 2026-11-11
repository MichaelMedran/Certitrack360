"""Alertas urgentes sin leer del usuario, para la franja «URGENTE» de todas las pantallas (RF-43)."""


def urgentes(request):
    """Lo completa el hito S3-H4: {"alertas_urgentes": [...]} con las alertas abiertas que el usuario no leyó."""
    return {"alertas_urgentes": []}
