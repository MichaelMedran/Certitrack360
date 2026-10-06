"""Ayudantes para las pruebas automatizadas."""
import shutil
import tempfile

from django.test import override_settings


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
