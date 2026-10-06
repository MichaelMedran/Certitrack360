import time

from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, connection
from django.db.migrations.executor import MigrationExecutor


def migraciones_pendientes():
    ejecutor = MigrationExecutor(connection)
    return bool(ejecutor.migration_plan(ejecutor.loader.graph.leaf_nodes()))


class Command(BaseCommand):
    help = (
        "Espera a que la base de datos acepte conexiones (y, con --migrado, a que tenga todas las migraciones aplicadas). "
        "Se usa al arrancar con Docker Compose, donde la base y la web inician a la vez."
    )

    def add_arguments(self, parser):
        parser.add_argument("--migrado", action="store_true", help="Espera también a que no queden migraciones pendientes.")
        parser.add_argument("--intentos", type=int, default=60, help="Cuántas veces reintentar (uno por segundo).")

    def handle(self, *args, **opts):
        for intento in range(1, opts["intentos"] + 1):
            try:
                connection.ensure_connection()
                if not (opts["migrado"] and migraciones_pendientes()):
                    self.stdout.write(self.style.SUCCESS("Base de datos lista."))
                    return
                motivo = "hay migraciones pendientes"
            except OperationalError as exc:
                connection.close()
                motivo = f"la base de datos no responde ({str(exc).splitlines()[0]})"
            self.stdout.write(f"Esperando ({intento}/{opts['intentos']}): {motivo}…")
            time.sleep(1)
        raise CommandError("La base de datos no estuvo lista a tiempo.")
