import copy

from django.conf import settings
from django.db import models
from django.utils.text import slugify


def ruta_archivo_tdr(instancia, nombre):
    """fichas / contrato / nombre saneado."""
    contrato = instancia.contrato
    carpeta = f"{contrato.pk}-{slugify(contrato.numero_contrato)[:30] or 'contrato'}"
    return f"fichas/{carpeta}/{nombre}"


class FichaLevantamiento(models.Model):
    """Ficha de levantamiento del TDR (SDD del Sprint 2, RF-30: HU-14 y HU-06).

    Registra los datos del TDR, el estado documental inicial y los ítems de entregables recurrentes.
    Mientras está en BORRADOR la puede redactar el junior asignado al contrato, el senior del contrato,
    el gerente o el admin. La confirmación la realiza solo el senior responsable del contrato, el gerente
    o el admin: congela `estado_inicial` (que nunca más se modifica) y genera los entregables.
    """

    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        CONFIRMADA = "CONFIRMADA", "Confirmada"

    class EstadoDocumental(models.TextChoices):
        ABIERTO = "ABIERTO", "Abierto"
        EN_CURSO = "EN_CURSO", "En curso"
        COMPLETO = "COMPLETO", "Completo"

    contrato = models.ForeignKey(
        "clientes.Contrato", on_delete=models.PROTECT, related_name="fichas", verbose_name="contrato"
    )
    id_tdr = models.CharField("ID-TDR", max_length=50)
    archivo_tdr = models.FileField("archivo del TDR", upload_to=ruta_archivo_tdr, max_length=255)
    nombre_archivo_tdr = models.CharField("nombre del archivo del TDR", max_length=255)
    requerimientos = models.TextField("requerimientos del servicio")
    formatos = models.CharField("formatos a presentar", max_length=255, blank=True)
    frecuencia_reportes = models.CharField("frecuencia de reportes", max_length=100, blank=True)
    penalidades = models.TextField("penalidades por incumplimiento", blank=True)
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="fichas_a_cargo", verbose_name="responsable"
    )
    documentos_disponibles = models.TextField("documentos disponibles", blank=True)
    documentos_faltantes = models.TextField("documentos faltantes", blank=True)
    formato_esperado = models.CharField("formato esperado", max_length=150, blank=True)
    fecha_limite = models.DateField("fecha límite", null=True, blank=True)
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.BORRADOR)
    # Foto de todos los campos al confirmar (HU-06): nunca se modifica después de la confirmación.
    estado_inicial = models.JSONField(default=dict, blank=True)
    estado_documental = models.CharField(
        "estado documental", max_length=15, choices=EstadoDocumental.choices, default=EstadoDocumental.ABIERTO
    )
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="fichas_creadas"
    )
    confirmada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="fichas_confirmadas"
    )
    confirmada_en = models.DateTimeField(null=True, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-actualizada_en", "-id"]
        verbose_name = "ficha de levantamiento"
        verbose_name_plural = "fichas de levantamiento"

    def __str__(self):
        return f"Ficha {self.contrato.numero_contrato} · {self.id_tdr}"

    def save(self, *args, **kwargs):
        """Una vez confirmada la ficha, `estado_inicial` queda congelado y no se sobrescribe (HU-06)."""
        if self.pk:
            previa = type(self)._base_manager.filter(pk=self.pk).values("estado", "estado_inicial").first()
            if previa and previa["estado"] == self.Estado.CONFIRMADA and previa["estado_inicial"]:
                self.estado_inicial = copy.deepcopy(previa["estado_inicial"])
        super().save(*args, **kwargs)

    @property
    def confirmada(self):
        return self.estado == self.Estado.CONFIRMADA

    @property
    def cliente(self):
        return self.contrato.cliente


class ItemFicha(models.Model):
    """Ítem de entregable recurrente definido en la ficha de levantamiento (SDD del Sprint 2, §6.2 y §7.5)."""

    class Frecuencia(models.TextChoices):
        UNICA = "UNICA", "Única"
        SEMANAL = "SEMANAL", "Semanal"
        QUINCENAL = "QUINCENAL", "Quincenal"
        MENSUAL = "MENSUAL", "Mensual"
        TRIMESTRAL = "TRIMESTRAL", "Trimestral"

    ficha = models.ForeignKey(FichaLevantamiento, on_delete=models.CASCADE, related_name="items")
    nombre = models.CharField(max_length=150)
    plantilla = models.ForeignKey("clientes.PlantillaTDR", on_delete=models.PROTECT, related_name="items_ficha")
    frecuencia = models.CharField(max_length=15, choices=Frecuencia.choices, default=Frecuencia.MENSUAL)
    primera_fecha = models.DateField("primera fecha")
    hasta = models.DateField(null=True, blank=True)
    junior = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="items_ficha_junior"
    )
    senior = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="items_ficha_senior"
    )
    datos = models.JSONField(default=dict, blank=True)
    entregables_generados = models.ManyToManyField(
        "entregables.Entregable", blank=True, related_name="items_ficha"
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "ítem de ficha"
        verbose_name_plural = "ítems de ficha"

    def __str__(self):
        return f"{self.nombre} ({self.get_frecuencia_display()})"

    @property
    def senior_efectivo(self):
        return self.senior or self.ficha.contrato.senior_responsable

    @property
    def hasta_efectivo(self):
        return self.hasta or self.ficha.contrato.fecha_fin

    def datos_faltantes(self):
        """Etiquetas de los campos obligatorios de la plantilla que el ítem aún no tiene completos."""
        return [
            c["etiqueta"]
            for c in self.plantilla.campos_requeridos
            if str((self.datos or {}).get(c["nombre"], "")).strip() == ""
        ]
