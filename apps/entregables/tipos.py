"""Catálogos compartidos entre apps (sin modelos, para evitar importaciones circulares)."""
from django.db import models


class TipoAdjunto(models.TextChoices):
    TDR = "TDR", "TDR"
    BORRADOR = "BORRADOR", "Borrador"
    VERSION_FINAL = "VERSION_FINAL", "Versión final"
    EVIDENCIA = "EVIDENCIA", "Evidencia"
    OTRO = "OTRO", "Otro"
