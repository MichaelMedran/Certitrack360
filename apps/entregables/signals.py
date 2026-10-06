from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Adjunto


@receiver(post_delete, sender=Adjunto)
def borrar_archivo_del_disco(sender, instance, **kwargs):
    """Al borrar un adjunto (también en cascada) se elimina su archivo, una vez confirmada la transacción."""
    nombre, almacenamiento = instance.archivo.name, instance.archivo.storage
    if nombre:
        transaction.on_commit(lambda: almacenamiento.delete(nombre))
