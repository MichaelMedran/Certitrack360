from django.core.management.base import BaseCommand

from apps.conocimiento.servicios import indexar_lecciones


class Command(BaseCommand):
    help = "Convierte observaciones resueltas de entregables cerrados en lecciones aprendidas."

    def handle(self, *args, **opts):
        self.stdout.write(f"Lecciones nuevas: {indexar_lecciones()}")
