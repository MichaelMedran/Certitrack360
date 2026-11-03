"""Limpieza del archivo en disco al eliminar una VersionDocumento."""
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import VersionDocumento


@receiver(post_delete, sender=VersionDocumento)
def borrar_archivo_version(sender, instance, **kwargs):
    if instance.archivo and instance.archivo.name:
        storage, nombre = instance.archivo.storage, instance.archivo.name
        transaction.on_commit(lambda: storage.delete(nombre))
