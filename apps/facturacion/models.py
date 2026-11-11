"""Facturación (SDD del Sprint 3, §6.2): base de facturación simulada y verificaciones del número de factura (RF-46, HU-30)."""
from django.conf import settings
from django.db import models


class FacturaSimulada(models.Model):
    """Una factura de la base de facturación SIMULADA (HU-30 criterio 5): la plataforma solo la lee.

    Sirve para la demostración y las pruebas mientras Sistemas no autorice la conexión al sistema real; el conector
    simulado (`conector.ConectorSimulado`) es el único que la consulta.
    """

    class Estado(models.TextChoices):
        EMITIDA = "EMITIDA", "Emitida"
        PAGADA = "PAGADA", "Pagada"
        ANULADA = "ANULADA", "Anulada"

    numero = models.CharField("número", max_length=50, unique=True)
    cliente_nombre = models.CharField("cliente", max_length=150)
    contrato_numero = models.CharField("número de contrato", max_length=50)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.EMITIDA)
    fecha_emision = models.DateField("fecha de emisión")
    monto = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["numero"]
        verbose_name = "factura simulada"
        verbose_name_plural = "facturas simuladas"

    def __str__(self):
        return f"{self.numero} · {self.cliente_nombre}"


class VerificacionFactura(models.Model):
    """Una consulta del número de factura de un entregable. Nunca se edita ni se borra: el número vigente del entregable
    es el de su última verificación. La justificación de un senior se registra sobre la verificación que observó."""

    class Resultado(models.TextChoices):
        CORRECTA = "CORRECTA", "Correcta"
        NO_EXISTE = "NO_EXISTE", "No existe"
        OTRO_CLIENTE = "OTRO_CLIENTE", "Pertenece a otro cliente"
        OTRO_CONTRATO = "OTRO_CONTRATO", "Pertenece a otro contrato"
        ANULADA = "ANULADA", "Anulada"
        SIN_CONEXION = "SIN_CONEXION", "Sin conexión con facturación"

    entregable = models.ForeignKey("entregables.Entregable", on_delete=models.CASCADE, related_name="verificaciones_factura")
    numero = models.CharField("número de factura", max_length=50)
    resultado = models.CharField(max_length=14, choices=Resultado.choices)
    detalle = models.JSONField("respuesta de la consulta", default=dict, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    fecha = models.DateTimeField(auto_now_add=True)
    justificacion = models.TextField("justificación", blank=True)
    justificada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    justificada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "verificación de factura"
        verbose_name_plural = "verificaciones de factura"

    def __str__(self):
        return f"{self.numero}: {self.get_resultado_display()}"

    @property
    def correcta(self):
        return self.resultado == self.Resultado.CORRECTA

    @property
    def justificada(self):
        return bool(self.justificacion)
