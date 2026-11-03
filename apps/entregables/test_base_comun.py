"""SDD del Sprint 2, hito S2-H2 (base común): validación de archivos común a otras apps (§5) y ayudante de pruebas
`entregar` (§11.3). Las pruebas de adjuntos del Sprint 1 no cambian y siguen comprobando el mismo comportamiento."""
import ast
from pathlib import Path
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from apps.conocimiento.models import LeccionAprendida
from apps.entregables import adjuntos, archivos, servicios
from apps.entregables.models import Entregable, Observacion
from apps.entregables.testing import entregar
from apps.entregables.tests import Base

E = Entregable.Estado


class ValidarArchivoComunTests(SimpleTestCase):
    """SimpleTestCase no admite consultas a la base de datos: la validación no las necesita."""

    def error(self, archivo):
        with self.assertRaises(ValidationError) as ctx:
            archivos.validar_archivo(archivo)
        return ctx.exception.messages

    def test_adjuntos_usa_la_misma_funcion_y_conserva_sus_nombres(self):
        for nombre in ("validar_archivo", "sanear_nombre", "extensiones_permitidas", "tamano_maximo_bytes", "NOMBRE_MAX"):
            with self.subTest(nombre=nombre):
                self.assertIs(getattr(adjuntos, nombre), getattr(archivos, nombre))

    @override_settings(ALLOWED_UPLOAD_EXTENSIONS=["pdf", "docx"], MEDIA_MAX_UPLOAD_MB=1)
    def test_los_mensajes_no_cambian(self):
        self.assertEqual(self.error(SimpleUploadedFile("programa.exe", b"x")),
                         ["El archivo «programa.exe» no es de un tipo permitido. Formatos permitidos: pdf, docx."])
        self.assertEqual(self.error(SimpleUploadedFile("vacio.pdf", b"")), ["El archivo «vacio.pdf» está vacío."])
        self.assertEqual(self.error(SimpleUploadedFile("grande.pdf", b"x" * (2 * 1024 * 1024))),
                         ["El archivo «grande.pdf» pesa 2,0 MB y el máximo permitido es 1 MB."])

    def test_devuelve_el_nombre_saneado(self):
        self.assertEqual(archivos.validar_archivo(SimpleUploadedFile("../../informe técnico (v2).PDF", b"%PDF")),
                         "informe_técnico_v2.PDF")
        self.assertEqual(archivos.validar_archivo(SimpleUploadedFile("C:\\docs\\.acta.txt", b"x")), "acta.txt")

    def test_sirve_para_cualquier_archivo_sin_entregable(self):
        # La ficha de levantamiento (S2-H5) y el repositorio (S2-H9) la usarán con sus propios archivos.
        self.assertEqual(archivos.validar_archivo(ContentFile(b"hola", name="nota.txt")), "nota.txt")

    @override_settings(MEDIA_MAX_UPLOAD_MB=0.001)
    def test_el_limite_es_inclusivo_y_se_lee_de_la_configuracion(self):
        limite = archivos.tamano_maximo_bytes()
        self.assertEqual(limite, 1048)
        self.assertEqual(archivos.validar_archivo(SimpleUploadedFile("justo.pdf", b"x" * limite)), "justo.pdf")
        self.assertIn("máximo permitido", self.error(SimpleUploadedFile("pasado.pdf", b"x" * (limite + 1)))[0])

    def test_el_modulo_no_importa_modelos_ni_otras_apps(self):
        arbol = ast.parse(Path(archivos.__file__).read_text(encoding="utf-8"))
        modulos = []
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                modulos += [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                self.assertEqual(nodo.level, 0, "sin importaciones relativas dentro de la app")
                modulos.append(nodo.module)
        self.assertTrue(modulos)
        for modulo in modulos:
            with self.subTest(modulo=modulo):
                self.assertFalse(modulo.startswith("apps"))
                self.assertNotIn("models", modulo.split("."))


class LosAdjuntosUsanLaFuncionComunTests(Base):
    def test_la_subida_pasa_por_validar_archivo(self):
        with mock.patch("apps.entregables.adjuntos.validar_archivo", wraps=archivos.validar_archivo) as validar:
            a = adjuntos.subir(self.e1, self.j1, SimpleUploadedFile("../informe.pdf", b"%PDF"), "BORRADOR")
        validar.assert_called_once()
        self.assertEqual(a.nombre_original, "informe.pdf")

    def test_un_archivo_rechazado_no_crea_nada(self):
        with self.assertRaises(ValidationError) as ctx:
            adjuntos.subir(self.e1, self.j1, SimpleUploadedFile("programa.exe", b"x"), "OTRO")
        self.assertIn("no es de un tipo permitido", ctx.exception.messages[0])
        self.assertFalse(self.e1.adjuntos.exists())
        self.assertFalse(self.e1.historial.exists())


class AyudanteEntregarTests(Base):
    """Por ahora `entregar` es `servicios.mover(..., HECHO, ...)`; en el S2-H4 creará el cargo de recepción."""

    def aprobado(self, titulo="Aprobado"):
        return self.nuevo(self.c1, self.j1, self.s1, titulo, estado=E.LISTO_PARA_ENTREGA)

    def test_lleva_de_aprobado_a_entregado_con_el_servicio_de_siempre(self):
        e = self.aprobado()
        with mock.patch.object(servicios, "mover", wraps=servicios.mover) as mover:
            self.assertIs(entregar(e, self.s1), e)
        mover.assert_called_once_with(e, E.HECHO, self.s1)
        e.refresh_from_db()
        self.assertEqual(e.estado, E.HECHO)
        h = e.historial.get()
        self.assertEqual((h.estado_anterior, h.estado_nuevo, h.usuario), (E.LISTO_PARA_ENTREGA, E.HECHO, self.s1))

    def test_genera_las_lecciones_como_cualquier_cierre(self):
        e = self.aprobado()
        Observacion.objects.create(entregable=e, autor=self.s1, tipo_error="FORMATO", descripcion="Sin numeración",
                                   solucion="Se numeraron las páginas", resuelta=True)
        entregar(e, self.gerente)
        self.assertEqual(LeccionAprendida.objects.get().entregable_origen, e)

    def test_senior_del_entregable_gerente_y_admin_entregan(self):
        for usuario in (self.s1, self.gerente, self.admin):
            with self.subTest(usuario=usuario.username):
                self.assertEqual(entregar(self.aprobado(usuario.username), usuario).estado, E.HECHO)

    def test_respeta_los_permisos_y_el_flujo_como_mover(self):
        e = self.aprobado()
        for usuario in (self.j1, self.j2, self.s2):  # junior asignado, junior y senior ajenos
            with self.subTest(usuario=usuario.username), self.assertRaises(PermissionDenied):
                entregar(e, usuario)
        en_proceso = self.nuevo(self.c1, self.j1, self.s1, "En proceso", estado=E.EN_PROCESO)
        with self.assertRaises(ValidationError):
            entregar(en_proceso, self.s1)
        for x in (e, en_proceso):
            x.refresh_from_db()
        self.assertEqual((e.estado, en_proceso.estado), (E.LISTO_PARA_ENTREGA, E.EN_PROCESO))
