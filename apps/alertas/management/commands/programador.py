import logging

from django.core.management.base import BaseCommand

from apps.alertas.programador import crear_programador, tarea_alertas


class Command(BaseCommand):
    help = (
        "Deja corriendo las tareas programadas: alertas de vencimiento (cada hora) e indexación de lecciones "
        "del asistente (a diario). En Docker Compose es el servicio «programador»."
    )

    def handle(self, *args, **opts):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        programador = crear_programador()
        tarea_alertas()  # no esperar una hora a la primera revisión
        self.stdout.write(self.style.SUCCESS("Programador en marcha (Ctrl+C para detenerlo)."))
        try:
            programador.start()
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write("Programador detenido.")
