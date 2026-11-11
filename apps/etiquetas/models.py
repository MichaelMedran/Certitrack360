"""Etiquetas de colores para contratos y entregables (SDD del Sprint 3, RF-41, HU-23).

Las relaciones con contratos y entregables viven aquí (no en sus apps): así `entregables` y `clientes` no cambian de esquema
(RNF-17). El nombre de la relación inversa es `etiquetas_asignadas` porque `e.etiquetas` queda libre para la lista que arma
`servicios.enriquecer` en las tarjetas.
"""
from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


class Etiqueta(models.Model):
    class Color(models.TextChoices):
        # Lista cerrada de 8 colores con contraste comprobado (texto oscuro sobre fondo claro): ver static/css/s3-prioridad.css.
        GRIS = "GRIS", "Gris"
        AZUL = "AZUL", "Azul"
        VERDE = "VERDE", "Verde"
        AMBAR = "AMBAR", "Ámbar"
        ROJO = "ROJO", "Rojo"
        MORADO = "MORADO", "Morado"
        TURQUESA = "TURQUESA", "Turquesa"
        ROSA = "ROSA", "Rosa"

    nombre = models.CharField(max_length=40)
    color = models.CharField(max_length=10, choices=Color.choices, default=Color.GRIS)
    # La etiqueta de una línea de servicio (una migración crea una por línea existente; las líneas nuevas la reciben al crearse).
    linea_servicio = models.OneToOneField(
        "clientes.LineaServicio", null=True, blank=True, on_delete=models.SET_NULL, related_name="etiqueta",
        verbose_name="línea de servicio",
    )
    activa = models.BooleanField(
        default=True, help_text="Una etiqueta de baja deja de ofrecerse, pero se conserva donde ya estaba."
    )
    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    creada_en = models.DateTimeField(auto_now_add=True)
    contratos = models.ManyToManyField("clientes.Contrato", blank=True, related_name="etiquetas_asignadas")
    entregables = models.ManyToManyField("entregables.Entregable", blank=True, related_name="etiquetas_asignadas")

    class Meta:
        ordering = [Lower("nombre"), "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("nombre"), name="etiqueta_nombre_unico",
                violation_error_message="Ya existe una etiqueta con ese nombre.",
            ),
        ]

    def __str__(self):
        return self.nombre

    @property
    def clase_css(self):
        """Clase de color de la hoja de estilos (el nombre siempre se muestra en texto: el color solo refuerza)."""
        return f"etq-{self.color.lower()}"
