from django.conf import settings
from django.db import models


class Notificacion(models.Model):
    class Tipo(models.TextChoices):
        VENCIMIENTO = "VENCIMIENTO", "Vencimiento"
        OBSERVACION = "OBSERVACION", "Observación"
        ASIGNACION = "ASIGNACION", "Asignación"

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificaciones")
    entregable = models.ForeignKey("entregables.Entregable", on_delete=models.CASCADE, related_name="notificaciones")
    mensaje = models.CharField(max_length=255)
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    # Para VENCIMIENTO: umbral (días) que la originó; evita duplicados por umbral.
    umbral = models.IntegerField(null=True, blank=True)
    leida = models.BooleanField(default=False)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada_en", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "entregable", "umbral"],
                condition=models.Q(tipo="VENCIMIENTO"),
                name="una_alerta_por_umbral",
            )
        ]

    def __str__(self):
        return self.mensaje
