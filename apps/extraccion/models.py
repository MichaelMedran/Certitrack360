from django.conf import settings
from django.db import models


class Extraccion(models.Model):
    """Una lectura de un documento (PDF o imagen) con los datos que se propusieron (SDD del Sprint 3, §6.2 y §7.9).

    Es solo una propuesta: no toca ningún entregable hasta que la persona la confirma en la vista previa (`aplicada_en`).
    Cada usuario ve únicamente las suyas.
    """

    class Motor(models.TextChoices):
        TEXTO_PDF = "TEXTO_PDF", "Texto del PDF"
        TESSERACT = "TESSERACT", "OCR Tesseract"
        NINGUNO = "NINGUNO", "Ninguno"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    archivo = models.FileField(upload_to="extracciones/", max_length=255)
    nombre_original = models.CharField("nombre del archivo", max_length=255)
    motor = models.CharField(max_length=10, choices=Motor.choices, default=Motor.NINGUNO)
    texto = models.TextField(blank=True)
    # Lista de {clave, etiqueta, tipo, valor, confianza, origen, estado[, opciones][, confirmado]}; ver servicios.py.
    campos = models.JSONField(default=list, blank=True)
    ilegible = models.BooleanField(default=False)
    avisos = models.JSONField(default=list, blank=True)
    plantilla = models.ForeignKey(
        "clientes.PlantillaTDR", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        help_text="Plantilla cuyos campos se buscaron en el documento.",
    )
    entregable = models.ForeignKey(
        "entregables.Entregable", null=True, blank=True, on_delete=models.SET_NULL, related_name="extracciones",
        help_text="Vacío si se usó en «Nuevo entregable» y todavía no se creó el entregable.",
    )
    aplicada_en = models.DateTimeField(null=True, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada_en"]
        verbose_name = "extracción"
        verbose_name_plural = "extracciones"

    def __str__(self):
        return f"{self.nombre_original} ({self.get_motor_display()})"

    @property
    def aplicada(self):
        return self.aplicada_en is not None
