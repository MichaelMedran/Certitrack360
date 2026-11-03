"""Modelos del repositorio de plantillas y ejemplos anonimizados (SDD del Sprint 2, RF-34 y RF-35: HU-07 y HU-20, §6.2)."""
from django.conf import settings
from django.db import models
from django.utils.text import slugify


class DocumentoRepositorio(models.Model):
    """Documento del repositorio: plantilla de cliente (o genérica si `cliente` es nulo) o ejemplo anonimizado."""

    class Categoria(models.TextChoices):
        PLANTILLA_CLIENTE = "PLANTILLA_CLIENTE", "Plantilla de cliente"
        EJEMPLO_ANONIMIZADO = "EJEMPLO_ANONIMIZADO", "Ejemplo anonimizado"

    class TipoDocumento(models.TextChoices):
        TDR = "TDR", "TDR"
        CARTA = "CARTA", "Carta"
        REPORTE = "REPORTE", "Reporte"
        COTIZACION = "COTIZACION", "Cotización"
        OTRO = "OTRO", "Otro"

    titulo = models.CharField("título", max_length=200)
    categoria = models.CharField(
        "categoría",
        max_length=25,
        choices=Categoria.choices,
        default=Categoria.PLANTILLA_CLIENTE,
    )
    cliente = models.ForeignKey(
        "clientes.Cliente",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="documentos_repositorio",
        verbose_name="cliente",
    )
    tipo_documento = models.CharField("tipo de documento", max_length=15, choices=TipoDocumento.choices)
    linea_servicio = models.ForeignKey(
        "clientes.LineaServicio",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="documentos_repositorio",
        verbose_name="línea de servicio",
    )
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["titulo", "-id"]
        verbose_name = "documento del repositorio"
        verbose_name_plural = "documentos del repositorio"

    def __str__(self):
        return self.titulo

    @property
    def es_anonimizado(self):
        return self.categoria == self.Categoria.EJEMPLO_ANONIMIZADO

    @property
    def es_generica(self):
        return self.categoria == self.Categoria.PLANTILLA_CLIENTE and self.cliente_id is None

    @property
    def version_vigente(self):
        if "versiones" in getattr(self, "_prefetched_objects_cache", {}):
            for v in self.versiones.all():
                if v.vigente:
                    return v
            return None
        return self.versiones.filter(vigente=True).first()


def ruta_documento_repositorio(instancia, nombre):
    """Guarda los ejemplos anonimizados en `repositorio/anonimizados/` y las plantillas en `repositorio/clientes/` (§6.2)."""
    doc = instancia.documento
    slug = slugify(doc.titulo)[:30] or "documento"
    if doc.categoria == DocumentoRepositorio.Categoria.EJEMPLO_ANONIMIZADO:
        return f"repositorio/anonimizados/doc-{doc.pk}-{slug}/v{instancia.numero}_{nombre}"
    subcarpeta = f"cliente-{doc.cliente_id}" if doc.cliente_id else "genericas"
    return f"repositorio/clientes/{subcarpeta}/doc-{doc.pk}-{slug}/v{instancia.numero}_{nombre}"


class VersionDocumento(models.Model):
    """Versión de un documento del repositorio. Exactamente una versión es `vigente=True` por documento."""

    documento = models.ForeignKey(
        DocumentoRepositorio,
        on_delete=models.CASCADE,
        related_name="versiones",
        verbose_name="documento",
    )
    numero = models.PositiveIntegerField("n.º de versión", default=1)
    archivo = models.FileField(upload_to=ruta_documento_repositorio, max_length=255)
    nombre_original = models.CharField("nombre del archivo", max_length=255)
    comentario = models.CharField("comentario", max_length=255, blank=True)
    vigente = models.BooleanField(default=True)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    subido_en = models.DateTimeField(auto_now_add=True)
    verificacion_anonimizacion = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-numero", "-id"]
        verbose_name = "versión de documento"
        verbose_name_plural = "versiones de documento"
        constraints = [
            models.UniqueConstraint(
                fields=["documento", "numero"],
                name="version_documento_numero_unico",
            ),
            models.UniqueConstraint(
                fields=["documento"],
                condition=models.Q(vigente=True),
                name="version_documento_vigente_unica",
            ),
        ]

    def __str__(self):
        return f"{self.documento.titulo} · v{self.numero}"


class RegistroAccesoDocumento(models.Model):
    """Registro de auditoría de cada carga, descarga y restauración en el repositorio (RF-34, RF-35)."""

    class Accion(models.TextChoices):
        CARGA = "CARGA", "Carga"
        DESCARGA = "DESCARGA", "Descarga"
        RESTAURACION = "RESTAURACION", "Restauración"

    version = models.ForeignKey(
        VersionDocumento,
        on_delete=models.CASCADE,
        related_name="accesos",
        verbose_name="versión",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name="usuario",
    )
    accion = models.CharField("acción", max_length=15, choices=Accion.choices)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "registro de acceso a documento"
        verbose_name_plural = "registros de acceso a documentos"

    def __str__(self):
        return f"{self.get_accion_display()} · {self.version} · {self.usuario}"
