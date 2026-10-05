from django.conf import settings
from django.db import models

from apps.entregables.tipos import TipoAdjunto


class Cliente(models.Model):
    class Sector(models.TextChoices):
        BANCA = "BANCA", "Banca"
        TELECOM = "TELECOM", "Telecomunicaciones"
        PUBLICO = "PUBLICO", "Sector público"

    nombre = models.CharField(max_length=150, unique=True)
    sector = models.CharField(max_length=10, choices=Sector.choices)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Contrato(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="contratos")
    numero_contrato = models.CharField("número de contrato", max_length=50, unique=True)
    descripcion = models.CharField("descripción", max_length=255, blank=True)
    fecha_inicio = models.DateField("fecha de inicio")
    fecha_fin = models.DateField("fecha de fin")
    senior_responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="contratos_a_cargo",
        verbose_name="senior responsable",
        limit_choices_to={"rol": "SENIOR"},
    )
    juniors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="contratos_asignados",
        blank=True,
        limit_choices_to={"rol": "JUNIOR"},
    )
    activo = models.BooleanField(
        default=True, help_text="La baja es lógica: el contrato conserva su historial pero no admite entregables nuevos."
    )

    class Meta:
        ordering = ["numero_contrato"]

    def __str__(self):
        return f"{self.numero_contrato} · {self.cliente}"


class PlantillaTDR(models.Model):
    """Define los campos obligatorios que exige un tipo de entregable.

    campos_requeridos: lista de {"nombre": "slug", "etiqueta": "Texto", "tipo": "texto|texto_largo|numero|fecha|opcion"};
    los campos de tipo «opcion» llevan además "opciones": ["A", "B", ...].
    """

    TIPOS_CAMPO = ("texto", "texto_largo", "numero", "fecha", "opcion")

    cliente = models.ForeignKey(
        Cliente, null=True, blank=True, on_delete=models.CASCADE, related_name="plantillas",
        help_text="Déjelo vacío para una plantilla genérica.",
    )
    nombre = models.CharField(max_length=150)
    formato = models.CharField("formato del entregable", max_length=100, blank=True, help_text="Ej.: Informe en PDF")
    campos_requeridos = models.JSONField(default=list, blank=True)
    adjuntos_requeridos = models.JSONField(
        "adjuntos obligatorios", default=list, blank=True,
        help_text="Tipos de adjunto que el entregable debe tener antes de pasar a Verificación senior.",
    )
    plazo_dias_por_defecto = models.PositiveIntegerField("plazo por defecto (días)", default=10)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "plantilla TDR"
        verbose_name_plural = "plantillas TDR"

    def __str__(self):
        return f"{self.nombre} ({self.cliente or 'genérica'})"

    @property
    def adjuntos_requeridos_etiquetas(self):
        etiquetas = dict(TipoAdjunto.choices)
        return [str(etiquetas.get(t, t)) for t in self.adjuntos_requeridos]
