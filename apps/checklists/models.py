"""Checklists del entregable (SDD del Sprint 3, §6.2): por TDR (RF-44, HU-25) y de control de calidad (RF-45, HU-26)."""
from django.conf import settings
from django.db import models


class ItemChecklistTDR(models.Model):
    """Un requisito, documento o formato que el TDR exige para un entregable (§7.5).

    Nace de la ficha de levantamiento del contrato (origen FICHA) o lo agrega a mano un responsable (MANUAL). Cada cambio
    de estado guarda quién lo marcó y cuándo, y puede enlazar el adjunto del mismo entregable que lo sustenta.
    """

    class Tipo(models.TextChoices):
        REQUISITO = "REQUISITO", "Requisito"
        DOCUMENTO = "DOCUMENTO", "Documento"
        FORMATO = "FORMATO", "Formato"

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        EN_REVISION = "EN_REVISION", "En revisión"
        CUMPLIDO = "CUMPLIDO", "Cumplido"

    class Origen(models.TextChoices):
        FICHA = "FICHA", "Ficha del TDR"
        MANUAL = "MANUAL", "Agregado a mano"

    entregable = models.ForeignKey("entregables.Entregable", on_delete=models.CASCADE, related_name="checklist_tdr")
    texto = models.CharField("requisito", max_length=300)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.REQUISITO)
    obligatorio = models.BooleanField(default=True)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    marcado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    marcado_en = models.DateTimeField(null=True, blank=True)
    adjunto = models.ForeignKey(
        "entregables.Adjunto", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="documento que lo sustenta", help_text="Versión de un adjunto del mismo entregable.",
    )
    origen = models.CharField(max_length=6, choices=Origen.choices, default=Origen.MANUAL)
    orden = models.PositiveIntegerField(default=0)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["orden", "id"]
        verbose_name = "ítem del checklist por TDR"
        verbose_name_plural = "ítems del checklist por TDR"

    def __str__(self):
        return f"{self.get_tipo_display()}: {self.texto}"

    @property
    def cumplido(self):
        return self.estado == self.Estado.CUMPLIDO


class ItemCalidad(models.Model):
    """Ítem configurable del checklist de control de calidad (§7.6). Sin cliente aplica a todos los clientes."""

    class Categoria(models.TextChoices):
        INFORMACION_COMPLETA = "INFORMACION_COMPLETA", "Información completa"
        CONSISTENCIA = "CONSISTENCIA", "Consistencia de datos"
        FECHAS_VIGENCIA = "FECHAS_VIGENCIA", "Fechas y vigencia de documentos"
        FORMATO = "FORMATO", "Formato exigido por el cliente"
        OTRO = "OTRO", "Otro"

    cliente = models.ForeignKey(
        "clientes.Cliente", on_delete=models.CASCADE, null=True, blank=True, related_name="items_calidad",
        help_text="Vacío: el ítem aplica a todos los clientes.",
    )
    texto = models.CharField("qué se verifica", max_length=300)
    categoria = models.CharField("categoría", max_length=22, choices=Categoria.choices, default=Categoria.OTRO)
    obligatorio = models.BooleanField(default=True)
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["orden", "id"]
        verbose_name = "ítem de calidad"
        verbose_name_plural = "ítems de calidad"

    def __str__(self):
        return self.texto


class RevisionCalidad(models.Model):
    """Una aplicación del checklist de calidad a un entregable en Revisión senior. Nunca se edita: otra revisión es otro
    registro (HU-26 criterio 5: revisor, fecha, hora y resultado).

    `paso` es el registro del historial del paso a «Revisión senior» en el que se hizo: identifica el ciclo de revisión.
    Una revisión de un ciclo anterior no sirve para aprobar (§7.1).
    """

    class Resultado(models.TextChoices):
        CONFORME = "CONFORME", "Conforme"
        NO_CONFORME = "NO_CONFORME", "No conforme"

    entregable = models.ForeignKey("entregables.Entregable", on_delete=models.CASCADE, related_name="revisiones_calidad")
    revisor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    fecha = models.DateTimeField(auto_now_add=True)
    resultado = models.CharField(max_length=12, choices=Resultado.choices)
    paso = models.ForeignKey(
        "entregables.HistorialEstado", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "revisión de calidad"
        verbose_name_plural = "revisiones de calidad"

    def __str__(self):
        return f"{self.get_resultado_display()} · {self.entregable}"

    @property
    def conforme(self):
        return self.resultado == self.Resultado.CONFORME


class RespuestaCalidad(models.Model):
    """Respuesta a un ítem dentro de una revisión. Copia el texto y la obligatoriedad del ítem en ese momento, para que
    editar o dar de baja el ítem después no cambie lo que se revisó."""

    revision = models.ForeignKey(RevisionCalidad, on_delete=models.CASCADE, related_name="respuestas")
    item = models.ForeignKey(ItemCalidad, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    texto = models.CharField(max_length=300)
    obligatorio = models.BooleanField(default=True)
    resultado = models.CharField(max_length=12, choices=RevisionCalidad.Resultado.choices)
    observacion = models.TextField("observación", blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(resultado="CONFORME") | ~models.Q(observacion=""),
                name="no_conforme_con_observacion",
                violation_error_message="Un ítem no conforme lleva su observación.",
            ),
        ]

    def __str__(self):
        return f"{self.texto}: {self.get_resultado_display()}"
