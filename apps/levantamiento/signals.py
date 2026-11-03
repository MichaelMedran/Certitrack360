from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import FichaLevantamiento


@receiver(post_delete, sender=FichaLevantamiento)
def borrar_archivo_tdr_del_disco(sender, instance, **kwargs):
    """Al borrar una ficha se elimina su archivo del TDR del disco una vez confirmada la transacción."""
    nombre, almacenamiento = instance.archivo_tdr.name, instance.archivo_tdr.storage
    if nombre:
        transaction.on_commit(lambda: almacenamiento.delete(nombre))
