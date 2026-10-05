from django.conf import settings
from django.db import models


class TipoError(models.TextChoices):
    DATO_FALTANTE = "DATO_FALTANTE", "Dato faltante"
    FORMATO = "FORMATO", "Formato"
    PLAZO = "PLAZO", "Plazo"
    CONTENIDO = "CONTENIDO", "Contenido"
    OTRO = "OTRO", "Otro"


class Entregable(models.Model):
    class Estado(models.TextChoices):
        A_REALIZAR = "A_REALIZAR", "A realizar"
        EN_PROCESO = "EN_PROCESO", "En proceso"
        VERIFICACION_SENIOR = "VERIFICACION_SENIOR", "Verificación senior"
        LISTO_PARA_ENTREGA = "LISTO_PARA_ENTREGA", "Listo para entrega"
        HECHO = "HECHO", "Hecho"

    contrato = models.ForeignKey("clientes.Contrato", on_delete=models.PROTECT, related_name="entregables")
    plantilla = models.ForeignKey("clientes.PlantillaTDR", on_delete=models.PROTECT, related_name="entregables")
    titulo = models.CharField("título", max_length=200)
    datos = models.JSONField(default=dict, blank=True)
    plazo = models.DateField()
    estado = models.CharField(max_length=25, choices=Estado.choices, default=Estado.A_REALIZAR)
    junior_asignado = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entregables_asignados",
        verbose_name="junior asignado",
    )
    senior_revisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entregables_a_revisar",
        verbose_name="senior revisor",
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entregables_creados"
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["plazo", "id"]

    def __str__(self):
        return self.titulo

    @property
    def cliente(self):
        return self.contrato.cliente

    def datos_etiquetados(self):
        """Pares (etiqueta, valor) según los campos de la plantilla."""
        return [(c["etiqueta"], self.datos.get(c["nombre"], "")) for c in self.plantilla.campos_requeridos]


class Observacion(models.Model):
    entregable = models.ForeignKey(Entregable, on_delete=models.CASCADE, related_name="observaciones")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    tipo_error = models.CharField("tipo de error", max_length=20, choices=TipoError.choices)
    descripcion = models.TextField("descripción")
    solucion = models.TextField("solución", blank=True)
    resuelta = models.BooleanField(default=False)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada_en"]
        verbose_name_plural = "observaciones"

    def __str__(self):
        return f"{self.get_tipo_error_display()} · {self.entregable}"


class HistorialEstado(models.Model):
    entregable = models.ForeignKey(Entregable, on_delete=models.CASCADE, related_name="historial")
    estado_anterior = models.CharField(max_length=25, choices=Entregable.Estado.choices, blank=True)
    estado_nuevo = models.CharField(max_length=25, choices=Entregable.Estado.choices)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]
