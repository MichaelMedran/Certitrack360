from django.conf import settings
from django.db import models
from django.utils import timezone


class Penalidad(models.Model):
    """Penalidad que el cliente aplicó (o anunció) por un entregable: lo que realmente se incurrió, no lo que dice el TDR."""

    entregable = models.ForeignKey("entregables.Entregable", on_delete=models.CASCADE, related_name="penalidades")
    motivo = models.CharField(max_length=255)
    monto = models.DecimalField("monto (S/)", max_digits=12, decimal_places=2, null=True, blank=True)
    fecha = models.DateField(default=timezone.localdate)
    registrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    registrada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "penalidad"
        verbose_name_plural = "penalidades"

    def __str__(self):
        return f"{self.entregable} · {self.motivo}"


class DocumentoVigencia(models.Model):
    """Documento del cliente que vence (certificado ISO, póliza, licencia): se avisa antes y al vencer."""

    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.CASCADE, related_name="documentos_vigencia")
    nombre = models.CharField(max_length=150)
    vence = models.DateField("fecha de vencimiento")
    notas = models.CharField(max_length=255, blank=True, default="")
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)
    # Marcas de los dos avisos (antes de vencer y al vencer): cada uno sale una sola vez por fecha de vencimiento.
    aviso_previo_en = models.DateTimeField(null=True, blank=True)
    aviso_vencido_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["vence", "nombre"]
        verbose_name = "documento con vigencia"
        verbose_name_plural = "documentos con vigencia"

    def __str__(self):
        return f"{self.nombre} ({self.cliente})"
