"""Ayudantes para las pruebas automatizadas."""
import shutil
import tempfile

from django.test import override_settings

from . import servicios
from .models import Entregable


def entregar(entregable, usuario):
    """Lleva un entregable de «Aprobado» (LISTO_PARA_ENTREGA) a «Entregado» (HECHO) y lo devuelve.

    Hoy (hito S2-H2) solo llama a `servicios.mover(entregable, HECHO, usuario)`, que es lo que hacen las pruebas del
    Sprint 1, así que sirve tal cual: valida la transición y el permiso igual que `mover` (ValidationError o
    PermissionDenied).

    En el hito S2-H4 (RF-29) el paso a Entregado exigirá el cargo de recepción. Entonces este ayudante creará el cargo
    (un adjunto CARGO_RECEPCION ficticio, con fecha y medio de entrega) y usará el servicio de entrega en lugar de `mover`,
    y las pruebas que cierran entregables lo usarán (SDD del Sprint 2, §11.3) sin cambiar nada más. Mientras tanto, las
    pruebas del Sprint 1 no se tocan.
    """
    return servicios.mover(entregable, Entregable.Estado.HECHO, usuario)


class MediaTemporal:
    """Las pruebas que escriben archivos usan una carpeta temporal como MEDIA_ROOT y la borran al terminar,
    para no ensuciar el directorio `media/` real."""

    @classmethod
    def setUpClass(cls):
        cls._carpeta_media = tempfile.mkdtemp(prefix="certitrack-media-")
        cls._override_media = override_settings(MEDIA_ROOT=cls._carpeta_media)
        cls._override_media.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override_media.disable()
        shutil.rmtree(cls._carpeta_media, ignore_errors=True)
