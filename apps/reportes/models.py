"""Reportes de avance (SDD del Sprint 3, RF-50 y §6.2). Solo gerente y admin; todo se calcula y guarda en el servidor local."""
import datetime
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def ruta_reporte(instancia, nombre):
    """Los PDF viven en MEDIA_ROOT/reportes/ y solo se descargan por una vista con permiso (MEDIA_URL es None)."""
    fecha = timezone.localtime(instancia.datos_al or timezone.now())
    return f"reportes/reporte-avance-{fecha:%Y%m%d-%H%M}-{uuid.uuid4().hex[:8]}.pdf"


class ReporteAvance(models.Model):
    class Origen(models.TextChoices):
        AUTOMATICO = "AUTOMATICO", "Automático"
        MANUAL = "MANUAL", "A pedido"

    origen = models.CharField(max_length=10, choices=Origen.choices)
    generado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Vacío en los reportes automáticos.",
    )
    generado_en = models.DateTimeField(auto_now_add=True)
    datos_al = models.DateTimeField("datos al", help_text="Fecha y hora a las que se leyeron los registros.")
    datos = models.JSONField(help_text="Todas las cifras del reporte, tal como se calcularon.")
    archivo = models.FileField(upload_to=ruta_reporte, max_length=255)

    class Meta:
        ordering = ["-datos_al", "-id"]
        verbose_name = "reporte de avance"
        verbose_name_plural = "reportes de avance"

    def __str__(self):
        return f"Reporte de avance del {timezone.localtime(self.datos_al):%d/%m/%Y %H:%M}"


class ConfiguracionReporte(models.Model):
    """Una sola fila: cuándo se genera el reporte automático."""

    class Periodicidad(models.TextChoices):
        DIARIA = "DIARIA", "Diaria"
        SEMANAL = "SEMANAL", "Semanal"
        MENSUAL = "MENSUAL", "Mensual"
        DESACTIVADA = "DESACTIVADA", "Desactivada"

    DIAS_SEMANA = [(0, "Lunes"), (1, "Martes"), (2, "Miércoles"), (3, "Jueves"), (4, "Viernes"), (5, "Sábado"), (6, "Domingo")]

    periodicidad = models.CharField(max_length=12, choices=Periodicidad.choices, default=Periodicidad.SEMANAL)
    dia_semana = models.PositiveSmallIntegerField("día de la semana", choices=DIAS_SEMANA, default=0)
    dia_mes = models.PositiveSmallIntegerField("día del mes", default=1, help_text="De 1 a 28, para que exista en todos los meses.")
    hora = models.TimeField(default=datetime.time(8, 0), help_text="Hora de Lima.")
    ultimo_automatico = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "configuración de reportes"
        verbose_name_plural = "configuración de reportes"

    def __str__(self):
        return f"Reportes {self.get_periodicidad_display().lower()}"

    @classmethod
    def cargar(cls):
        """La única fila de configuración; si no existe se crea (semanal, lunes, 08:00).

        Al crearla se anota el momento actual como `ultimo_automatico`: así el primer reporte automático sale en la próxima
        hora programada y no apenas arranca el programador.
        """
        config = cls.objects.order_by("pk").first()
        if config is None:
            config = cls.objects.create(ultimo_automatico=timezone.now())
        return config
