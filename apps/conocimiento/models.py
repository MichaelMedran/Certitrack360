from django.db import models

from apps.entregables.models import TipoError


class LeccionAprendida(models.Model):
    entregable_origen = models.ForeignKey(
        "entregables.Entregable", null=True, blank=True, on_delete=models.SET_NULL, related_name="lecciones"
    )
    observacion_origen = models.OneToOneField(
        "entregables.Observacion", null=True, blank=True, on_delete=models.SET_NULL, related_name="leccion"
    )
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.CASCADE, related_name="lecciones")
    tipo_error = models.CharField(max_length=20, choices=TipoError.choices)
    problema = models.TextField()
    solucion = models.TextField()
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada_en"]
        verbose_name_plural = "lecciones aprendidas"

    def __str__(self):
        return f"{self.get_tipo_error_display()} · {self.cliente}"
