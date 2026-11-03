"""Catálogos compartidos entre apps (sin modelos, para evitar importaciones circulares)."""
from django.db import models


class TipoAdjunto(models.TextChoices):
    TDR = "TDR", "TDR"
    BORRADOR = "BORRADOR", "Borrador"
    VERSION_FINAL = "VERSION_FINAL", "Versión final"
    EVIDENCIA = "EVIDENCIA", "Evidencia"
    OTRO = "OTRO", "Otro"
    # Sprint 2 (RF-29): los crea el registro de la entrega y del acta, no la subida de adjuntos. No son adjuntos
    # requeridos del Poka-Yoke ni tipos de documento que se versionen a mano (ver TIPOS_DE_SUBIDA).
    CARGO_RECEPCION = "CARGO_RECEPCION", "Cargo de recepción"
    ACTA_CONFORMIDAD = "ACTA_CONFORMIDAD", "Acta de conformidad"


#: Tipos de la entrega: se crean con «Marcar como entregado» y «Registrar acta»; nacen bloqueados.
TIPOS_DE_ENTREGA = (TipoAdjunto.CARGO_RECEPCION, TipoAdjunto.ACTA_CONFORMIDAD)

#: Tipos que el usuario sube, versiona y restaura (formulario de subida, adjuntos requeridos de la plantilla).
TIPOS_DE_SUBIDA = [(valor, etiqueta) for valor, etiqueta in TipoAdjunto.choices if valor not in TIPOS_DE_ENTREGA]
