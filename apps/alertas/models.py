from django.conf import settings
from django.db import models
from django.urls import reverse

from .enlaces import MENSAJE_ENLACE, es_enlace_interno, validar_enlace_interno


class Notificacion(models.Model):
    """Aviso automático dentro de la plataforma (no hay mensajes entre personas).

    Desde el Sprint 2 (hito S2-H2) un aviso puede no ser de un entregable: entonces lleva a `enlace`, una ruta interna
    (p. ej. la ficha de levantamiento que espera confirmación), o se muestra sin enlace. Ver `destino`.
    """

    class Tipo(models.TextChoices):
        VENCIMIENTO = "VENCIMIENTO", "Vencimiento"
        OBSERVACION = "OBSERVACION", "Observación"
        ASIGNACION = "ASIGNACION", "Asignación"
        VERIFICACION = "VERIFICACION", "Verificación"  # aviso al senior: un entregable espera su revisión
        # Tipos del Sprint 2 (SDD del Sprint 2, §6.1). Los genera cada hito al construir su pantalla.
        CORRECCION = "CORRECCION", "Corrección"  # se registró la acción correctiva de una observación (RF-25)
        ACTA = "ACTA", "Acta"  # el acta de conformidad sigue pendiente (RF-29)
        REASIGNACION = "REASIGNACION", "Reasignación"  # cambió el responsable principal (RF-31)
        INCORPORACION = "INCORPORACION", "Incorporación"  # plan de incorporación (RF-38)
        FICHA = "FICHA", "Ficha"  # una ficha de levantamiento espera confirmación (RF-30)
        # Tipos del Sprint 3 (SDD del Sprint 3, §6.1).
        URGENTE = "URGENTE", "Urgente"  # alerta de urgencia fuera de horario (RF-43)
        REPORTE = "REPORTE", "Reporte"  # se generó un reporte de avance (RF-50)
        CHECKLIST = "CHECKLIST", "Checklist"  # checklist por TDR o de calidad (RF-44, RF-45)
        FACTURA = "FACTURA", "Factura"  # verificación del número de factura (RF-46)
        VIGENCIA = "VIGENCIA", "Vigencia"  # un certificado o documento del cliente está por vencer o venció

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificaciones")
    # Opcional desde el Sprint 2: los avisos que no son de un entregable llevan `enlace`.
    entregable = models.ForeignKey(
        "entregables.Entregable", on_delete=models.CASCADE, related_name="notificaciones", null=True, blank=True
    )
    # Ruta interna a la que lleva «Ver» (p. ej. /calendario/). Vacío: el detalle del entregable o, sin él, ningún enlace.
    enlace = models.CharField(max_length=255, blank=True, default="", validators=[validar_enlace_interno])
    mensaje = models.CharField(max_length=255)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
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
            ),
            # La restricción anterior no cambia. Esta asegura que siga cubriendo todo aviso de vencimiento: con el
            # entregable vacío la base de datos no compararía la fila con las demás.
            models.CheckConstraint(
                condition=models.Q(entregable__isnull=False) | ~models.Q(tipo="VENCIMIENTO"),
                name="vencimiento_con_entregable",
                violation_error_message="Un aviso de vencimiento siempre es de un entregable.",
            ),
            # Lo esencial del enlace también en la base de datos: cubre bulk_create y update, que no pasan por save().
            models.CheckConstraint(
                condition=models.Q(enlace="") | (models.Q(enlace__startswith="/") & ~models.Q(enlace__startswith="//")),
                name="enlace_es_ruta_interna",
                violation_error_message=MENSAJE_ENLACE,
            ),
        ]

    def __str__(self):
        return self.mensaje

    def save(self, *args, **kwargs):
        """Ninguna alta o edición guarda un enlace que no sea una ruta interna (lanza ValidationError).

        Si solo se actualizan otros campos (p. ej. al marcarla como leída) el enlace no se vuelve a validar: un dato
        antiguo no debe impedir marcar el aviso.
        """
        campos = kwargs.get("update_fields")
        if campos is None or "enlace" in campos:
            validar_enlace_interno(self.enlace)
        super().save(*args, **kwargs)

    @property
    def destino(self):
        """Ruta de «Ver»: el enlace, si lo tiene; si no, el detalle de su entregable; si no tiene ninguno, "" (el aviso
        se muestra sin enlace). El enlace se vuelve a comprobar: nunca se muestra uno que no sea una ruta interna."""
        if self.enlace and es_enlace_interno(self.enlace):
            return self.enlace
        if self.entregable_id:
            return reverse("entregable_detalle", args=[self.entregable_id])
        return ""


class EnvioWhatsApp(models.Model):
    """Copia de un aviso enviada (o por enviar) al celular del colaborador por WhatsApp. Ver `apps/alertas/whatsapp.py`."""

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        ENVIANDO = "ENVIANDO", "Enviando"
        ENVIADO = "ENVIADO", "Enviado"
        FALLIDO = "FALLIDO", "Fallido"

    notificacion = models.OneToOneField(Notificacion, on_delete=models.CASCADE, related_name="envio_whatsapp")
    numero = models.CharField("número", max_length=15)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE, db_index=True)
    intentos = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=500, blank=True, default="")
    id_externo = models.CharField("identificador del proveedor", max_length=100, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)
    enviado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "envío por WhatsApp"
        verbose_name_plural = "envíos por WhatsApp"

    def __str__(self):
        return f"{self.numero} · {self.get_estado_display()}"
