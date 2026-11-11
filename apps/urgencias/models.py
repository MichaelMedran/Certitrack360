"""Alerta de urgencia fuera de horario (SDD del Sprint 3, RF-43, HU-28, §6.2 y §7.4).

Lo que otros módulos (la prioridad calculada, S3-H3) necesitan saber es una sola cosa: si el entregable tiene una alerta
**abierta** (sin `cerrada_en`). Para eso usan `AlertaUrgente.objects.abiertas()` o `servicios.ids_con_alerta_abierta`.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q


class AlertaUrgenteQuerySet(models.QuerySet):
    def abiertas(self):
        return self.filter(cerrada_en__isnull=True)


class AlertaUrgente(models.Model):
    entregable = models.ForeignKey("entregables.Entregable", on_delete=models.CASCADE, related_name="alertas_urgentes")
    naturaleza = models.TextField("naturaleza de la urgencia")
    plazo_esperado = models.DateTimeField("plazo esperado")
    # Se calcula al activar con `settings.HORARIO_LABORAL` (lunes a viernes de 09:00 a 18:00, hora de Lima).
    fuera_de_horario = models.BooleanField("fuera de horario", default=False)
    activada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    activada_en = models.DateTimeField(auto_now_add=True)
    aceptada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    aceptada_en = models.DateTimeField(null=True, blank=True)
    cerrada_en = models.DateTimeField(null=True, blank=True)
    # Quiénes recibieron el aviso «URGENTE» al activarla (guardia, senior responsable, senior revisor, junior asignado).
    # Se guardan para poder decir «2 de 4 confirmaron» aunque después cambien los responsables.
    destinatarios = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="alertas_urgentes_recibidas")

    objects = AlertaUrgenteQuerySet.as_manager()

    class Meta:
        ordering = ["-activada_en", "-id"]
        verbose_name = "alerta urgente"
        verbose_name_plural = "alertas urgentes"
        constraints = [
            # A lo sumo una alerta sin cerrar por entregable (también lo exige el servicio, con un mensaje claro).
            models.UniqueConstraint(
                fields=["entregable"], condition=Q(cerrada_en__isnull=True), name="una_alerta_abierta_por_entregable",
            ),
        ]

    def __str__(self):
        return f"URGENTE · {self.entregable.codigo}"

    @property
    def abierta(self):
        return self.cerrada_en is None


class LecturaAlerta(models.Model):
    """Confirmación de lectura: quién y cuándo. Única por alerta y usuario."""

    alerta = models.ForeignKey(AlertaUrgente, on_delete=models.CASCADE, related_name="lecturas")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    leida_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["leida_en", "id"]
        constraints = [
            models.UniqueConstraint(fields=["alerta", "usuario"], name="una_lectura_por_alerta_y_usuario"),
        ]

    def __str__(self):
        return f"{self.usuario} leyó la alerta {self.alerta_id}"
