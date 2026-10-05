from django.core.management.base import BaseCommand

from apps.alertas.servicios import generar_alertas


class Command(BaseCommand):
    help = "Genera las notificaciones de vencimiento (programar a diario, o cada hora; es idempotente)."

    def handle(self, *args, **opts):
        n = generar_alertas()
        self.stdout.write(f"Notificaciones creadas: {n}")
