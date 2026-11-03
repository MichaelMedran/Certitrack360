from django.conf import settings
from django.db import models, router, transaction
from django.utils import timezone
from django.utils.text import Truncator, slugify

from .tipos import TipoAdjunto


def generar_codigo(pk, creado_en):
    """Código único del entregable (SDD del Sprint 2, RF-20): <prefijo>-<año de creación>-<id con 5 dígitos>.

    El año es el de la fecha local (America/Lima) de creación; el id garantiza que no se repita aunque cambie el prefijo.
    """
    return f"{settings.CODIGO_PREFIJO}-{timezone.localtime(creado_en).year}-{pk:05d}"


class TipoError(models.TextChoices):
    DATO_FALTANTE = "DATO_FALTANTE", "Dato faltante"
    FORMATO = "FORMATO", "Formato"
    PLAZO = "PLAZO", "Plazo"
    CONTENIDO = "CONTENIDO", "Contenido"
    OTRO = "OTRO", "Otro"


class Entregable(models.Model):
    class Estado(models.TextChoices):
        # Etiquetas de HU-04 (SDD del Sprint 2, RF-23). Los códigos guardados son los del Sprint 1 y no cambian.
        A_REALIZAR = "A_REALIZAR", "Por hacer"
        EN_PROCESO = "EN_PROCESO", "En proceso"
        VERIFICACION_SENIOR = "VERIFICACION_SENIOR", "Revisión senior"
        LISTO_PARA_ENTREGA = "LISTO_PARA_ENTREGA", "Aprobado"
        HECHO = "HECHO", "Entregado"

    # Se asigna al crear, en la misma transacción, por cualquier camino (formulario, panel técnico, seed_demo...): ver save().
    codigo = models.CharField("código", max_length=30, unique=True, null=True, blank=True, editable=False)
    contrato = models.ForeignKey("clientes.Contrato", on_delete=models.PROTECT, related_name="entregables")
    plantilla = models.ForeignKey("clientes.PlantillaTDR", on_delete=models.PROTECT, related_name="entregables")
    titulo = models.CharField("título", max_length=200)
    # Datos de recepción (HU-01): obligatorios en el formulario «Nuevo entregable», opcionales en la base de datos.
    id_tdr = models.CharField("ID-TDR", max_length=50, blank=True, default="")
    fecha_recepcion = models.DateField("fecha de recepción", null=True, blank=True)
    datos = models.JSONField(default=dict, blank=True)
    plazo = models.DateField()
    estado = models.CharField(max_length=25, choices=Estado.choices, default=Estado.A_REALIZAR)
    junior_asignado = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entregables_asignados",
        verbose_name="junior asignado",
    )
    senior_revisor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entregables_a_revisar",
        verbose_name="senior revisor",
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entregables_creados"
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["plazo", "id"]

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        """Al crear: fecha de recepción por defecto (la fecha local de creación) y código único.

        El código lleva el id, que existe recién después del INSERT; por eso ambas escrituras van en una transacción y no
        queda ningún entregable sin código. Las ediciones posteriores no lo tocan.
        """
        alta = self._state.adding
        if alta and self.fecha_recepcion is None:
            self.fecha_recepcion = timezone.localdate()
        if not alta or self.codigo:
            return super().save(*args, **kwargs)
        base = kwargs.get("using") or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=base):
            super().save(*args, **kwargs)
            self.codigo = generar_codigo(self.pk, self.creado_en)
            type(self)._base_manager.using(base).filter(pk=self.pk).update(codigo=self.codigo)

    @property
    def referencia(self):
        """Código y título para los avisos: CT-2026-00031 «Informe técnico 03» (el título, acotado)."""
        titulo = Truncator(self.titulo).chars(150)
        return f"{self.codigo} «{titulo}»" if self.codigo else f"«{titulo}»"

    @property
    def cliente(self):
        return self.contrato.cliente

    @property
    def urgencia(self):
        """VENCIDO, CRITICO, PROXIMO o NORMAL, calculada al momento (no se guarda)."""
        from .urgencia import calcular

        return calcular(self.plazo, self.estado)

    @property
    def urgencia_etiqueta(self):
        from .urgencia import ETIQUETAS

        return ETIQUETAS[self.urgencia]

    def datos_etiquetados(self):
        """Pares (etiqueta, valor) según los campos de la plantilla."""
        return [(c["etiqueta"], self.datos.get(c["nombre"], "")) for c in self.plantilla.campos_requeridos]


class Observacion(models.Model):
    entregable = models.ForeignKey(Entregable, on_delete=models.CASCADE, related_name="observaciones")
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    tipo_error = models.CharField("tipo de error", max_length=20, choices=TipoError.choices)
    descripcion = models.TextField("descripción")
    solucion = models.TextField("solución", blank=True)
    resuelta = models.BooleanField(default=False)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada_en"]
        verbose_name_plural = "observaciones"

    def __str__(self):
        return f"{self.get_tipo_error_display()} · {self.entregable}"


class HistorialEstado(models.Model):
    """Historial del entregable: cambios de estado y acciones relevantes.

    Una subida o eliminación de adjunto se registra con el estado actual como anterior y nuevo
    (el estado no cambia) y la descripción en `detalle`.
    """

    entregable = models.ForeignKey(Entregable, on_delete=models.CASCADE, related_name="historial")
    estado_anterior = models.CharField(max_length=25, choices=Entregable.Estado.choices, blank=True)
    estado_nuevo = models.CharField(max_length=25, choices=Entregable.Estado.choices)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    fecha = models.DateTimeField(auto_now_add=True)
    detalle = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    @property
    def es_cambio_de_estado(self):
        return self.estado_anterior != self.estado_nuevo

    @property
    def descripcion(self):
        """Texto para mostrar: «Estado: A → B» (más el detalle, si lo hay) o solo el detalle de la acción."""
        if not self.es_cambio_de_estado and self.detalle:
            return self.detalle
        anterior = self.get_estado_anterior_display() or "—"
        texto = f"Estado: {anterior} → {self.get_estado_nuevo_display()}"
        return f"{texto} ({self.detalle})" if self.detalle else texto


def ruta_adjunto(instancia, nombre):
    """cliente / contrato / entregable / tipo_vN_nombre. El nombre ya viene saneado desde el servicio."""
    entregable = instancia.entregable
    contrato = entregable.contrato
    cliente = f"{contrato.cliente_id}-{slugify(contrato.cliente.nombre)[:30] or 'cliente'}"
    carpeta_contrato = f"{contrato.pk}-{slugify(contrato.numero_contrato)[:30] or 'contrato'}"
    return f"{cliente}/{carpeta_contrato}/entregable-{entregable.pk}/{instancia.tipo.lower()}_v{instancia.version}_{nombre}"


class Adjunto(models.Model):
    """Documento de un entregable. Cada subida del mismo tipo crea una versión nueva; nada se sobrescribe."""

    entregable = models.ForeignKey(Entregable, on_delete=models.CASCADE, related_name="adjuntos")
    archivo = models.FileField(upload_to=ruta_adjunto, max_length=255)
    nombre_original = models.CharField("nombre del archivo", max_length=255)
    tipo = models.CharField(max_length=15, choices=TipoAdjunto.choices)
    version = models.PositiveIntegerField(default=1)
    comentario = models.CharField(max_length=255, blank=True)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    subido_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tipo", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["entregable", "tipo", "version"], name="adjunto_version_unica"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} v{self.version} · {self.nombre_original}"
