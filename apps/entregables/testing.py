"""Ayudantes para las pruebas automatizadas."""
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from . import adjuntos, entregas
from .models import Entrega
from .tipos import TipoAdjunto


def pdf_ficticio(nombre="archivo.pdf"):
    """Un archivo PDF diminuto y ficticio para las pruebas."""
    return ContentFile(b"%PDF-1.4 ficticio", name=nombre)


def entregar(entregable, usuario, fecha_entrega=None, medio=Entrega.Medio.CORREO, version_enviada=None):
    """Lleva un entregable de «Aprobado» (LISTO_PARA_ENTREGA) a «Entregado» (HECHO) y lo devuelve.

    Desde el hito S2-H4 (RF-29) el paso a Entregado exige el cargo de recepción, así que este ayudante crea un cargo
    ficticio y usa el servicio de entrega (`entregas.registrar`), igual que la interfaz: valida el permiso y la transición
    como `mover` (ValidationError o PermissionDenied) y bloquea la versión enviada. Si el entregable no tiene una versión
    final, crea una ficticia (la que se «envía»). Los tests que cierran entregables lo usan (SDD del Sprint 2, §11.3).
    """
    with transaction.atomic():  # si el servicio rechaza la entrega, tampoco queda la versión final ficticia
        if version_enviada is None and adjuntos.vigente(entregable, TipoAdjunto.VERSION_FINAL) is None:
            adjuntos.crear_adjunto(entregable, usuario, pdf_ficticio("version_final.pdf"), TipoAdjunto.VERSION_FINAL,
                                   "Versión aprobada para entrega")
        entregas.registrar(
            entregable, usuario, fecha_entrega or timezone.localdate(), medio, pdf_ficticio("cargo.pdf"),
            version_enviada=version_enviada,
        )
    return entregable


def aprobar(entregable, usuario):
    """Lleva un entregable de «Revisión senior» (VERIFICACION_SENIOR) a «Aprobado» (LISTO_PARA_ENTREGA) y lo devuelve.

    Desde el Sprint 3 (RF-45) aprobar exige una revisión de calidad conforme del ciclo actual: este ayudante la registra
    (todos los ítems aplicables en Conforme) y luego llama a `mover`, igual que la interfaz. Las pruebas y el seed que
    aprueban entregables lo usan (SDD del Sprint 3, §11.3).
    """
    from . import servicios

    try:
        from apps.checklists.calidad import registrar_conforme
    except ImportError:  # el módulo de calidad aún no existe
        registrar_conforme = None
    if registrar_conforme is not None:
        registrar_conforme(entregable, usuario)
    return servicios.mover(entregable, entregable.Estado.LISTO_PARA_ENTREGA, usuario)


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
