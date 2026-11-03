"""Modelos del plan de incorporación por rol (SDD del Sprint 2, §6.2 y §7.12, RF-38: HU-15)."""
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.cuentas.models import Usuario


class PlanIncorporacion(models.Model):
    """Lista de actividades de incorporación definida por rol y puesto opcional."""

    nombre = models.CharField(max_length=150)
    rol = models.CharField(max_length=10, choices=Usuario.Rol.choices, default=Usuario.Rol.JUNIOR)
    puesto = models.CharField(max_length=100, blank=True, default="")
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre", "-id"]
        verbose_name = "plan de incorporación"
        verbose_name_plural = "planes de incorporación"

    def __str__(self):
        return f"{self.nombre} ({self.get_rol_display()})"


class ActividadPlan(models.Model):
    """Actividad operativa de un plan de incorporación con enlace al material vigente."""

    plan = models.ForeignKey(PlanIncorporacion, on_delete=models.CASCADE, related_name="actividades")
    orden = models.PositiveIntegerField(default=1)
    semana = models.PositiveIntegerField(default=1)
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    documento = models.ForeignKey(
        "repositorio.DocumentoRepositorio",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    procedimiento = models.ForeignKey(
        "conocimiento.Procedimiento",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    enlace_interno = models.CharField(max_length=200, blank=True)
    etiqueta_recurso = models.CharField(max_length=150, blank=True)
    rol_responsable = models.CharField(max_length=60, default="Senior asignado")
    como_se_comprueba = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["semana", "orden", "id"]
        verbose_name = "actividad de incorporación"
        verbose_name_plural = "actividades de incorporación"

    def __str__(self):
        return f"{self.orden}. {self.titulo}"

    @property
    def version_vigente(self):
        if self.documento_id and self.documento:
            return self.documento.version_vigente
        return None

    @property
    def url_recurso(self):
        """Enlace al recurso: apunta siempre a la versión vigente del documento o procedimiento (§7.12)."""
        if self.documento_id and self.documento:
            vig = self.documento.version_vigente
            if vig is not None:
                return reverse("repositorio_descargar", args=[vig.pk])
            return reverse("repositorio_documento", args=[self.documento_id])
        if self.procedimiento_id:
            return f"{reverse('repositorio')}?pestana=procedimientos#proc-{self.procedimiento_id}"
        return self.enlace_interno or ""

    @property
    def url_detalle_documento(self):
        if self.documento_id:
            return reverse("repositorio_documento", args=[self.documento_id])
        return ""

    @property
    def nombre_recurso(self):
        if self.documento_id and self.documento:
            vig = self.documento.version_vigente
            base = self.etiqueta_recurso or self.documento.titulo
            return f"{base} (v{vig.numero})" if vig is not None else base
        if self.procedimiento_id and self.procedimiento:
            return self.etiqueta_recurso or self.procedimiento.titulo
        if self.etiqueta_recurso:
            return self.etiqueta_recurso
        if self.enlace_interno:
            return self.enlace_interno
        return "—"


class Incorporacion(models.Model):
    """Asignación de un plan de incorporación a un colaborador ingresante con su responsable."""

    plan = models.ForeignKey(PlanIncorporacion, on_delete=models.PROTECT, related_name="incorporaciones")
    ingresante = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="incorporaciones",
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="incorporaciones_a_cargo",
    )
    fecha_inicio = models.DateField(default=timezone.localdate)
    confirmada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    confirmada_en = models.DateTimeField(null=True, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada_en", "-id"]
        verbose_name = "incorporación"
        verbose_name_plural = "incorporaciones"

    def __str__(self):
        return f"{self.ingresante} · {self.plan.nombre}"

    @property
    def confirmada(self):
        return self.confirmada_en is not None

    @property
    def lista_avances(self):
        return list(
            self.avances.select_related(
                "actividad__documento",
                "actividad__procedimiento",
            ).order_by("actividad__semana", "actividad__orden", "actividad__id")
        )

    @property
    def total_actividades(self):
        return self.avances.count()

    @property
    def completadas_count(self):
        return self.avances.filter(estado=AvanceActividad.Estado.COMPLETADA).count()

    @property
    def porcentaje_avance(self):
        total = self.total_actividades
        if not total:
            return 0
        return round((self.completadas_count * 100) / total)

    @property
    def todas_completadas(self):
        total = self.total_actividades
        return total > 0 and self.completadas_count == total


class AvanceActividad(models.Model):
    """Estado de avance de una actividad para un ingresante concreto."""

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        EN_CURSO = "EN_CURSO", "En curso"
        COMPLETADA = "COMPLETADA", "Completada"

    incorporacion = models.ForeignKey(Incorporacion, on_delete=models.CASCADE, related_name="avances")
    actividad = models.ForeignKey(ActividadPlan, on_delete=models.PROTECT, related_name="avances")
    estado = models.CharField(max_length=15, choices=Estado.choices, default=Estado.PENDIENTE)
    actualizado_en = models.DateTimeField(auto_now=True)
    completada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["actividad__semana", "actividad__orden", "actividad__id"]
        verbose_name = "avance de actividad"
        verbose_name_plural = "avances de actividad"
        constraints = [
            models.UniqueConstraint(fields=["incorporacion", "actividad"], name="avance_actividad_unico"),
        ]

    def __str__(self):
        return f"{self.incorporacion.ingresante} · {self.actividad.titulo} ({self.get_estado_display()})"
