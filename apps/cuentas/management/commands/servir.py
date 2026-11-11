from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Arranca CertiTrack 360 con el servidor de producción (waitress). Los archivos estáticos los sirve WhiteNoise, "
        "así que no hace falta otro servidor web. Reemplaza a «runserver», que es solo para desarrollo (RF-51)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--host", default="0.0.0.0", help="Dirección en que escucha (por defecto, todas las de la máquina).")
        parser.add_argument("--puerto", type=int, default=settings.SERVIDOR_PUERTO,
                            help=f"Puerto (por defecto SERVIDOR_PUERTO = {settings.SERVIDOR_PUERTO}).")
        parser.add_argument("--hilos", type=int, default=settings.SERVIDOR_HILOS,
                            help=f"Hilos de atención (por defecto SERVIDOR_HILOS = {settings.SERVIDOR_HILOS}).")
        parser.add_argument("--sin-estaticos", action="store_true",
                            help="No recopila los archivos estáticos antes de arrancar (ya están en STATIC_ROOT).")

    def handle(self, *args, **opts):
        from waitress import create_server

        from certitrack.wsgi import application

        if not opts["sin_estaticos"]:
            call_command("collectstatic", interactive=False, verbosity=0)
        servidor = create_server(application, host=opts["host"], port=opts["puerto"], threads=opts["hilos"])
        self.stdout.write(self.style.SUCCESS(
            f"CertiTrack 360 escuchando en http://{opts['host']}:{opts['puerto']}/ con {opts['hilos']} hilos. Ctrl+C para detener."))
        try:
            servidor.run()
        except KeyboardInterrupt:
            self.stdout.write("Servidor detenido.")
        finally:
            servidor.close()
