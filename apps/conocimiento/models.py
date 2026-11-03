from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.entregables.models import TipoError


class LeccionAprendida(models.Model):
    """Problema detectado en un entregable junto con su solución (SDD §9.2). Se genera al cerrar el entregable."""

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
    # Índice vectorial local: embedding calculado por Ollama y el modelo que lo generó (se recalcula si cambia).
    embedding = models.JSONField(null=True, blank=True)
    embedding_modelo = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-creada_en"]
        verbose_name_plural = "lecciones aprendidas"

    def __str__(self):
        return f"{self.get_tipo_error_display()} · {self.cliente}"

    @property
    def texto_indexable(self):
        return f"{self.get_tipo_error_display()}. {self.problema} Solución: {self.solucion}"


class Procedimiento(models.Model):
    """Procedimiento aprobado que el asistente usa como fuente (SDD del Sprint 2, RF-37: HU-10)."""

    titulo = models.CharField(max_length=200)
    contenido = models.TextField()
    linea_servicio = models.ForeignKey(
        "clientes.LineaServicio",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="procedimientos",
    )
    documento = models.ForeignKey(
        "repositorio.DocumentoRepositorio",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="procedimientos",
    )
    aprobado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )
    aprobado_en = models.DateTimeField(default=timezone.now)
    vigente = models.BooleanField(default=True)
    embedding = models.JSONField(null=True, blank=True)
    embedding_modelo = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-aprobado_en", "titulo"]
        verbose_name_plural = "procedimientos"

    def __str__(self):
        return self.titulo

    def __getitem__(self, key):
        if key == "procedimiento":
            return self
        if key == "documento_visible":
            return getattr(self, "documento_visible", False)
        return getattr(self, key)

    @property
    def texto_indexable(self):
        return f"{self.titulo}. {self.contenido}"


class ConsultaAsistente(models.Model):
    """Consulta realizada al asistente por un usuario, con sus fuentes citadas y valoración (SDD del Sprint 2, RF-37)."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="consultas_asistente",
    )
    pregunta = models.CharField(max_length=500)
    respuesta = models.TextField(blank=True)
    fuentes = models.JSONField(default=dict, blank=True)
    util = models.BooleanField(null=True, blank=True)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada_en", "-id"]
        verbose_name_plural = "consultas al asistente"

    def __str__(self):
        return f"{self.usuario}: {self.pregunta[:50]}"
