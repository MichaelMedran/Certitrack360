"""Pruebas del repositorio de plantillas y ejemplos anonimizados (SDD del Sprint 2, hito S2-H9 · RF-34 y RF-35: HU-07 y HU-20; caso 25 de la §13)."""
import shutil
import tempfile
from pathlib import Path

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from apps.clientes.models import Cliente, Contrato, LineaServicio, PlantillaTDR
from apps.entregables.tests import Base
from apps.repositorio import servicios
from apps.repositorio.models import (
    DocumentoRepositorio,
    RegistroAccesoDocumento,
    VersionDocumento,
)
from apps.repositorio.visibilidad import documentos_visibles


def _archivo(nombre="formato.docx", contenido=b"contenido-de-prueba"):
    return SimpleUploadedFile(nombre, contenido, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


class Caso25RepositorioYPermisosTests(Base):
    """Caso 25 (§13): un junior no ve ni descarga plantillas de clientes ajenos; un anonimizado sin verificación se rechaza."""

    def setUp(self):
        super().setUp()
        self._tmp_media = tempfile.mkdtemp()
        self._override = override_settings(MEDIA_ROOT=Path(self._tmp_media))
        self._override.enable()

        self.cliente_ajeno = Cliente.objects.create(nombre="Banco Ajeno", sector="BANCA")
        self.c_ajeno = Contrato.objects.create(
            cliente=self.cliente_ajeno,
            numero_contrato="C-AJENO",
            fecha_inicio="2026-01-01",
            fecha_fin="2026-12-31",
            senior_responsable=self.s2,
        )
        self.c_ajeno.juniors.add(self.j2)
        self.linea_bpo = LineaServicio.objects.get(nombre="BPO")

        # Plantilla del cliente de C1 (visible para j1, s1, gerente, admin; NO visible para j2 ni s2)
        self.doc_c1, self.v_c1 = servicios.cargar_plantilla(
            self.s1,
            titulo="Formato de reporte mensual",
            tipo_documento=DocumentoRepositorio.TipoDocumento.REPORTE,
            archivo=_archivo("reporte_c1_v1.docx"),
            cliente=self.cliente,
            linea_servicio=self.linea_bpo,
            comentario="Versión inicial",
        )
        # Plantilla del cliente ajeno (visible para j2, s2, gerente, admin; NO visible para j1 ni s1)
        self.doc_ajeno, self.v_ajeno = servicios.cargar_plantilla(
            self.s2,
            titulo="Formato exclusivo Banco Ajeno",
            tipo_documento=DocumentoRepositorio.TipoDocumento.CARTA,
            archivo=_archivo("carta_ajena.docx"),
            cliente=self.cliente_ajeno,
            linea_servicio=self.linea_bpo,
        )
        # Plantilla genérica (visible para todos)
        self.doc_generico, self.v_generico = servicios.cargar_plantilla(
            self.gerente,
            titulo="Cotización estándar",
            tipo_documento=DocumentoRepositorio.TipoDocumento.COTIZACION,
            archivo=_archivo("cotizacion_estandar.docx"),
            cliente=None,
        )
        # Ejemplo anonimizado (visible para todos)
        self.doc_anon, self.v_anon = servicios.publicar_anonimizado(
            self.s1,
            titulo="Ejemplo de informe técnico aprobado",
            tipo_documento=DocumentoRepositorio.TipoDocumento.REPORTE,
            archivo=_archivo("ejemplo_anon.pdf", b"%PDF-1.4 ejemplo"),
            confirmaciones=servicios.CLAVES_NDA,
            linea_servicio=self.linea_bpo,
        )

    def tearDown(self):
        self._override.disable()
        shutil.rmtree(self._tmp_media, ignore_errors=True)
        super().tearDown()

    def test_caso_25_visibilidad_y_descarga_por_rol(self):
        # j1 ve la de su cliente, la genérica y el anonimizado; NO ve la de Banco Ajeno
        vis_j1 = set(documentos_visibles(self.j1).values_list("pk", flat=True))
        self.assertEqual(vis_j1, {self.doc_c1.pk, self.doc_generico.pk, self.doc_anon.pk})

        # s1 ve la de su cliente, la genérica y el anonimizado; NO ve la de Banco Ajeno
        vis_s1 = set(documentos_visibles(self.s1).values_list("pk", flat=True))
        self.assertEqual(vis_s1, {self.doc_c1.pk, self.doc_generico.pk, self.doc_anon.pk})

        # Gerente y Admin ven las cuatro
        for u in (self.gerente, self.admin):
            self.assertEqual(
                set(documentos_visibles(u).values_list("pk", flat=True)),
                {self.doc_c1.pk, self.doc_ajeno.pk, self.doc_generico.pk, self.doc_anon.pk},
            )

        # j1 intenta abrir o descargar la plantilla de Banco Ajeno -> 404 y no se registra descarga
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(reverse("repositorio_documento", args=[self.doc_ajeno.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("repositorio_descargar", args=[self.v_ajeno.pk])).status_code, 404)
        self.assertFalse(
            RegistroAccesoDocumento.objects.filter(
                version=self.v_ajeno,
                accion=RegistroAccesoDocumento.Accion.DESCARGA,
            ).exists()
        )

        # j1 sí descarga la de su cliente y el ejemplo anonimizado -> 200 y queda registrado en RegistroAccesoDocumento
        r_ok = self.client.get(reverse("repositorio_descargar", args=[self.v_c1.pk]))
        self.assertEqual(r_ok.status_code, 200)
        r_ok.close()
        self.assertTrue(
            RegistroAccesoDocumento.objects.filter(
                version=self.v_c1,
                usuario=self.j1,
                accion=RegistroAccesoDocumento.Accion.DESCARGA,
            ).exists()
        )

    def test_caso_25_publicar_anonimizado_exige_las_cuatro_confirmaciones_nda(self):
        # Con solo 2 de las 4 confirmaciones, el servidor rechaza con el mensaje exacto («faltan 2 confirmaciones»)
        self.client.force_login(self.s1)
        r = self.client.post(
            reverse("repositorio_nuevo"),
            {
                "categoria": DocumentoRepositorio.Categoria.EJEMPLO_ANONIMIZADO,
                "titulo": "Matriz sin confirmar NDA",
                "tipo_documento": DocumentoRepositorio.TipoDocumento.REPORTE,
                "linea_servicio": self.linea_bpo.pk,
                "archivo": _archivo("matriz.xlsx"),
                "nombres": "on",
                "montos": "on",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "No se puede publicar: faltan 2 confirmaciones de la lista.")
        self.assertFalse(DocumentoRepositorio.objects.filter(titulo="Matriz sin confirmar NDA").exists())

        # Con 3 de las 4 confirmaciones -> «falta 1 confirmación»
        with self.assertRaisesMessage(ValidationError, "No se puede publicar: falta 1 confirmación de la lista."):
            servicios.publicar_anonimizado(
                self.s1,
                titulo="Matriz incompleta",
                tipo_documento=DocumentoRepositorio.TipoDocumento.REPORTE,
                archivo=_archivo("matriz.xlsx"),
                confirmaciones=["nombres", "montos", "contratos"],
            )

        # Con las 4 confirmaciones -> se publica y guarda verificacion_anonimizacion y archivo en carpeta separada
        r_ok = self.client.post(
            reverse("repositorio_nuevo"),
            {
                "categoria": DocumentoRepositorio.Categoria.EJEMPLO_ANONIMIZADO,
                "titulo": "Matriz anonimizada completa",
                "tipo_documento": DocumentoRepositorio.TipoDocumento.REPORTE,
                "linea_servicio": self.linea_bpo.pk,
                "archivo": _archivo("matriz_anon.xlsx"),
                "nombres": "on",
                "montos": "on",
                "contratos": "on",
                "datos_personales": "on",
            },
        )
        self.assertEqual(r_ok.status_code, 302)
        doc_nuevo = DocumentoRepositorio.objects.get(titulo="Matriz anonimizada completa")
        vig = doc_nuevo.version_vigente
        self.assertEqual(set(vig.verificacion_anonimizacion["items_confirmados"]), set(servicios.CLAVES_NDA))
        self.assertEqual(vig.verificacion_anonimizacion["confirmado_por_id"], self.s1.pk)
        # Separación de carpetas en MEDIA_ROOT (§6.2): anonimizados vs clientes
        self.assertTrue(vig.archivo.name.startswith("repositorio/anonimizados/"))
        self.assertTrue(self.v_c1.archivo.name.startswith("repositorio/clientes/"))

    def test_permisos_de_escritura_por_rol(self):
        # Junior recibe 403 al intentar cargar plantilla o publicar anonimizado
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(reverse("repositorio_nuevo")).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("repositorio_nuevo"),
                {
                    "categoria": DocumentoRepositorio.Categoria.EJEMPLO_ANONIMIZADO,
                    "titulo": "Intento Junior",
                    "tipo_documento": DocumentoRepositorio.TipoDocumento.REPORTE,
                    "archivo": _archivo("j.pdf"),
                    "nombres": "on",
                    "montos": "on",
                    "contratos": "on",
                    "datos_personales": "on",
                },
            ).status_code,
            403,
        )

        # Senior recibe 403 si intenta cargar plantilla para un cliente ajeno o una genérica
        with self.assertRaises(PermissionDenied):
            servicios.cargar_plantilla(
                self.s1,
                titulo="Intrusa",
                tipo_documento=DocumentoRepositorio.TipoDocumento.CARTA,
                archivo=_archivo("intrusa.docx"),
                cliente=self.cliente_ajeno,
            )
        with self.assertRaises(PermissionDenied):
            servicios.cargar_plantilla(
                self.s1,
                titulo="Genérica por senior",
                tipo_documento=DocumentoRepositorio.TipoDocumento.CARTA,
                archivo=_archivo("gen.docx"),
                cliente=None,
            )

    def test_versionado_y_restauracion_crean_nueva_version_y_registran_acceso(self):
        # Subir v2 al documento de C1
        v2 = servicios.subir_nueva_version(
            self.doc_c1,
            self.s1,
            archivo=_archivo("reporte_c1_v2.docx", b"contenido-v2"),
            comentario="Nuevo logo y sección de riesgos",
            exigir_comentario=True,
        )
        self.v_c1.refresh_from_db()
        self.assertFalse(self.v_c1.vigente)
        self.assertTrue(v2.vigente)
        self.assertEqual(v2.numero, 2)
        self.assertEqual(self.doc_c1.version_vigente, v2)

        # Restaurar v1 como vigente desde la vista -> crea v3 con comentario «Restaurada desde la v1» y registra RESTAURACION
        self.client.force_login(self.s1)
        r = self.client.post(
            reverse("repositorio_documento", args=[self.doc_c1.pk]),
            {"accion": "restaurar", "version": self.v_c1.pk},
        )
        self.assertRedirects(r, reverse("repositorio_documento", args=[self.doc_c1.pk]))
        v2.refresh_from_db()
        self.assertFalse(v2.vigente)
        v3 = self.doc_c1.version_vigente
        self.assertEqual(v3.numero, 3)
        self.assertTrue(v3.vigente)
        self.assertEqual(v3.comentario, "Restaurada desde la v1")
        self.assertTrue(
            RegistroAccesoDocumento.objects.filter(
                version=v3,
                usuario=self.s1,
                accion=RegistroAccesoDocumento.Accion.RESTAURACION,
            ).exists()
        )

    def test_baja_logica_y_visibilidad_del_registro_de_accesos(self):
        url_doc = reverse("repositorio_documento", args=[self.doc_c1.pk])

        # Junior y Senior NO ven la tabla «Registro de cargas y descargas» y reciben 403 al intentar dar de baja
        for u in (self.j1, self.s1):
            self.client.force_login(u)
            r = self.client.get(url_doc)
            self.assertEqual(r.status_code, 200)
            self.assertNotContains(r, "Registro de cargas y descargas")
            self.assertEqual(self.client.post(url_doc, {"accion": "baja"}).status_code, 403)

        # Gerente y Admin SÍ ven el registro de cargas y descargas y pueden dar de baja el documento
        self.client.force_login(self.gerente)
        r_ger = self.client.get(url_doc)
        self.assertContains(r_ger, "Registro de cargas y descargas")
        r_baja = self.client.post(url_doc, {"accion": "baja"})
        self.assertRedirects(r_baja, reverse("repositorio"))
        self.doc_c1.refresh_from_db()
        self.assertFalse(self.doc_c1.activo)
        self.assertFalse(documentos_visibles(self.j1).filter(pk=self.doc_c1.pk).exists())

    def test_enlace_opcional_desde_plantilla_tdr_a_documento_formato(self):
        self.client.force_login(self.gerente)
        r = self.client.post(
            reverse("adm_editar", args=["plantillas", self.plantilla.pk]),
            {
                "nombre": self.plantilla.nombre,
                "cliente": "",
                "formato": "Word",
                "documento_formato": self.doc_c1.pk,
                "plazo_dias_por_defecto": 10,
                "campo_nombre": ["c_periodo"],
                "campo_etiqueta": ["Periodo"],
                "campo_tipo": ["texto"],
                "campo_opciones": [""],
            },
        )
        self.assertRedirects(r, reverse("adm_lista", args=["plantillas"]))
        self.plantilla.refresh_from_db()
        self.assertEqual(self.plantilla.documento_formato, self.doc_c1)
