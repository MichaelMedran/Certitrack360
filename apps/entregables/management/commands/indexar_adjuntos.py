from django.core.management.base import BaseCommand

from apps.entregables.models import Adjunto
from apps.entregables.texto import extraer_texto


class Command(BaseCommand):
    help = (
        "Lee el texto de los adjuntos que aún no lo tienen, para que el buscador encuentre dentro de su contenido. "
        "Los adjuntos nuevos se leen solos al subirlos; este comando sirve para los que ya existían."
    )

    def add_arguments(self, parser):
        parser.add_argument("--todos", action="store_true", help="Vuelve a leer también los que ya tienen texto.")

    def handle(self, *args, **opciones):
        adjuntos = Adjunto.objects.all() if opciones["todos"] else Adjunto.objects.filter(texto="")
        leidos = con_texto = 0
        for adjunto in adjuntos.iterator():
            leidos += 1
            try:
                with adjunto.archivo.open("rb") as archivo:
                    texto = extraer_texto(archivo, adjunto.nombre_original)
            except (OSError, ValueError):  # el archivo ya no está en el disco
                continue
            if texto != adjunto.texto:
                Adjunto.objects.filter(pk=adjunto.pk).update(texto=texto)
            con_texto += bool(texto)
        self.stdout.write(f"Adjuntos revisados: {leidos}. Con texto para buscar: {con_texto}.")
