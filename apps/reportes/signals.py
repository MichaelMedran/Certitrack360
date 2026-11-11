from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ReporteAvance


@receiver(post_delete, sender=ReporteAvance)
def borrar_pdf_del_disco(sender, instance, **kwargs):
    """Al borrar un reporte se elimina su PDF del disco, una vez confirmada la transacción."""
    nombre, almacenamiento = instance.archivo.name, instance.archivo.storage
    if nombre:
        transaction.on_commit(lambda: almacenamiento.delete(nombre))
