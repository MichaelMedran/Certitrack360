from django.core.management.base import BaseCommand

from apps.alertas.servicios import generar_alertas, generar_alertas_acta


class Command(BaseCommand):
    help = (
        "Genera las notificaciones de vencimiento y los avisos de acta de conformidad pendiente "
        "(programar a diario, o cada hora; es idempotente)."
    )

    def handle(self, *args, **opts):
        n = generar_alertas()
        self.stdout.write(f"Notificaciones creadas: {n}")
        actas = generar_alertas_acta()
        self.stdout.write(f"Avisos de acta pendiente creados: {actas}")
