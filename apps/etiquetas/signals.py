"""Cada línea de servicio nueva recibe su etiqueta (la migración 0002 crea las de las líneas que ya existían)."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.clientes.models import LineaServicio

from .models import Etiqueta
from .servicios import nombre_en_uso


def crear_etiqueta_de_linea(linea):
    """Crea la etiqueta de la línea si no la tiene y el nombre está libre (si no, queda sin etiqueta propia)."""
    if Etiqueta.objects.filter(linea_servicio=linea).exists() or nombre_en_uso(linea.nombre):
        return None
    colores = Etiqueta.Color.values
    return Etiqueta.objects.create(
        nombre=linea.nombre, color=colores[Etiqueta.objects.filter(linea_servicio__isnull=False).count() % len(colores)],
        linea_servicio=linea,
    )


@receiver(post_save, sender=LineaServicio, dispatch_uid="etiquetas_linea_nueva")
def al_guardar_linea(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        crear_etiqueta_de_linea(instance)
