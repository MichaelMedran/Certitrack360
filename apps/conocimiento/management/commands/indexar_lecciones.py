from django.core.management.base import BaseCommand

from apps.conocimiento.servicios import indexar_lecciones


class Command(BaseCommand):
    help = (
        "Genera las lecciones aprendidas de los entregables cerrados y calcula sus embeddings con Ollama local. "
        "Se puede ejecutar varias veces; también lo corre la tarea programada."
    )

    def handle(self, *args, **opts):
        nuevas, indexadas, aviso = indexar_lecciones()
        self.stdout.write(f"Lecciones nuevas: {nuevas} · Embeddings calculados: {indexadas}")
        if aviso:
            self.stderr.write(self.style.WARNING(aviso))
