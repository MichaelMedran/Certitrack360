"""Pruebas de la exportación a PDF y Excel (SDD del Sprint 3, RF-47: HU-27; caso 37 de la §13)."""
import datetime
import re
from io import BytesIO

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook, load_workbook
from pypdf import PdfReader

from apps.clientes.models import Cliente, Contrato, LineaServicio
from apps.entregables import adjuntos
from apps.entregables.models import Adjunto, HistorialEstado
from apps.entregables.tests import Base
from apps.entregables.tipos import TipoAdjunto
from apps.exportacion import excel, pdf, servicios
from apps.repositorio.models import DocumentoRepositorio, VersionDocumento

PERIODO = "Operación mensual del año niño"


def texto_pdf(contenido):
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(contenido)).pages)


def contenido_de(adjunto):
    with adjunto.archivo.open("rb") as f:
        return f.read()


class BaseExportacion(Base):
    def setUp(self):
        super().setUp()
        self.e1.id_tdr = "TDR-2026-007"
        self.e1.fecha_recepcion = datetime.date(2026, 11, 3)
        self.e1.plazo = datetime.date(2026, 11, 20)
        self.e1.datos = {"c_periodo": PERIODO, "c_nivel": "3"}
        self.e1.save()
        self.url_pdf = reverse("entregable_exportar", args=[self.e1.pk, "pdf"])
        self.url_excel = reverse("entregable_exportar", args=[self.e1.pk, "excel"])

    def formato_xlsx(self, celdas):
        """Enlaza a la plantilla un formato .xlsx del repositorio con las celdas indicadas ({"A1": texto})."""
        libro = Workbook()
        hoja = libro.active
        for ref, valor in celdas.items():
            hoja[ref] = valor
        salida = BytesIO()
        libro.save(salida)
        doc = DocumentoRepositorio.objects.create(
            titulo="Formato del cliente", cliente=self.cliente, tipo_documento="REPORTE", creado_por=self.gerente)
        VersionDocumento.objects.create(
            documento=doc, numero=1, archivo=ContentFile(salida.getvalue(), name="formato.xlsx"),
            nombre_original="formato.xlsx", vigente=True, subido_por=self.gerente)
        self.plantilla.documento_formato = doc
        self.plantilla.save()
        return doc


class PermisosYValidacionTests(BaseExportacion):
    def test_criterio_1_el_detalle_ofrece_exportar_a_pdf_y_excel(self):
        """HU-27 criterio 1: botón Exportar con las opciones PDF y Excel en la ficha."""
        self.client.force_login(self.j1)
        r = self.client.get(reverse("entregable_detalle", args=[self.e1.pk]))
        self.assertContains(r, 'id="exportar"')
        self.assertContains(r, "Exportar a PDF")
        self.assertContains(r, "Exportar a Excel")
        self.assertContains(r, self.url_pdf)
        self.assertContains(r, self.url_excel)
        ids = re.findall(r'\bid="([^"]+)"', r.content.decode())
        self.assertEqual(len(ids), len(set(ids)), f"IDs repetidos: {ids}")

    def test_permisos_404_si_no_lo_ve_y_403_si_lo_ve_sin_poder_exportar(self):
        for usuario in (self.j2, self.s2):  # ajenos: ni lo ven
            self.client.force_login(usuario)
            self.assertEqual(self.client.post(self.url_pdf).status_code, 404)
        self.assertEqual(Adjunto.objects.filter(tipo=TipoAdjunto.EXPORTACION).count(), 0)

    def test_responsables_gerente_y_admin_exportan(self):
        for usuario in (self.j1, self.s1, self.gerente, self.admin):
            with self.subTest(usuario=usuario.username):
                self.assertTrue(servicios.puede_exportar(usuario, self.e1))
                self.client.force_login(usuario)
                self.assertEqual(self.client.post(self.url_pdf).status_code, 200)
        for usuario in (self.j2, self.s2):
            self.assertFalse(servicios.puede_exportar(usuario, self.e1))

    def test_quien_lo_ve_pero_no_puede_exportar_recibe_403(self):
        """El servicio rechaza con PermissionDenied (403) y la vista lo traduce; no se crea ningún adjunto."""
        with self.assertRaises(PermissionDenied):
            servicios.exportar(self.e1, self.j2, "pdf")
        from unittest import mock
        self.client.force_login(self.j1)
        with mock.patch("apps.exportacion.servicios.puede_exportar", return_value=False):
            self.assertEqual(self.client.post(self.url_pdf).status_code, 403)
        self.assertEqual(Adjunto.objects.filter(tipo=TipoAdjunto.EXPORTACION).count(), 0)

    def test_exige_sesion_y_metodo_post_y_formato_conocido(self):
        self.assertEqual(self.client.post(self.url_pdf).status_code, 302)  # login
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(self.url_pdf).status_code, 405)
        self.assertEqual(self.client.post(reverse("entregable_exportar", args=[self.e1.pk, "word"])).status_code, 404)

    def test_criterio_3_faltantes_no_exporta_y_dice_cuales(self):
        """HU-27 criterio 3: sin obligatorios no exporta e indica cuáles; no se crea ningún adjunto."""
        self.e1.id_tdr = ""
        self.e1.fecha_recepcion = None
        self.e1.datos = {"c_periodo": "", "c_nivel": "3"}
        self.e1.save()
        self.assertEqual(servicios.faltantes(self.e1), ["ID-TDR", "Fecha de recepción", "Periodo"])
        with self.assertRaises(servicios.FaltanDatos) as ctx:
            servicios.exportar(self.e1, self.j1, "pdf")
        self.assertEqual(ctx.exception.faltantes, ["ID-TDR", "Fecha de recepción", "Periodo"])
        self.client.force_login(self.j1)
        for url in (self.url_pdf, self.url_excel):
            r = self.client.post(url, follow=True)
            self.assertEqual(r.redirect_chain[0][0], reverse("entregable_detalle", args=[self.e1.pk]) + "#exportar")
            self.assertContains(r, "No se puede exportar: falta completar ID-TDR, Fecha de recepción, Periodo.")
        self.assertContains(r, "No se puede exportar todavía.")
        self.assertEqual(Adjunto.objects.filter(tipo=TipoAdjunto.EXPORTACION).count(), 0)
        self.assertFalse(HistorialEstado.objects.filter(detalle__startswith="Exportó").exists())

    def test_el_adjunto_de_exportacion_no_se_sube_a_mano(self):
        archivo = SimpleUploadedFile("x.pdf", b"%PDF-1.4 x", content_type="application/pdf")
        with self.assertRaises(ValidationError):
            adjuntos.subir(self.e1, self.s1, archivo, TipoAdjunto.EXPORTACION)
        self.client.force_login(self.s1)
        r = self.client.post(reverse("adjunto_subir", args=[self.e1.pk]),
                             {"tipo": TipoAdjunto.EXPORTACION, "archivo": archivo})
        self.assertNotEqual(r.status_code, 500)
        self.assertEqual(Adjunto.objects.filter(tipo=TipoAdjunto.EXPORTACION).count(), 0)


class DatosConsolidadosTests(BaseExportacion):
    def test_datos_en_orden_con_periodo_en_espanol_y_campos_de_la_plantilla(self):
        linea = LineaServicio.objects.create(nombre="Línea de prueba")
        self.c1.linea_servicio = linea
        self.c1.save()
        datos = servicios.datos_consolidados(self.e1)
        claves = [c for c, _e, _v in datos]
        self.assertEqual(claves, ["codigo", "titulo", "cliente", "contrato", "linea_servicio", "id_tdr", "periodo",
                                  "fecha_recepcion", "plazo", "estado", "junior", "senior", "c_periodo", "c_nivel"])
        valores = {c: v for c, _e, v in datos}
        self.assertEqual(valores["periodo"], "noviembre de 2026")
        self.assertEqual(valores["fecha_recepcion"], "03/11/2026")
        self.assertEqual(valores["plazo"], "20/11/2026")
        self.assertEqual(valores["cliente"], "Cliente Demo")
        self.assertEqual(valores["linea_servicio"], "Línea de prueba")
        self.assertEqual(valores["c_periodo"], PERIODO)
        self.assertEqual({c: e for c, e, _v in datos}["c_nivel"], "Nivel")

    def test_periodo_para_cada_mes(self):
        for mes, nombre in enumerate(servicios.MESES, start=1):
            self.e1.plazo = datetime.date(2027, mes, 1)
            self.assertEqual(servicios.periodo(self.e1), f"{nombre} de 2027")


class PdfTests(BaseExportacion):
    def test_criterios_2_y_5_pdf_se_abre_con_pypdf_y_trae_los_datos_consolidados(self):
        """HU-27 criterios 2 y 5: carga cliente, periodo e información; abre en un visor de PDF."""
        self.client.force_login(self.s1)
        r = self.client.post(self.url_pdf)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertIn(f"{self.e1.codigo}_v1.pdf", r["Content-Disposition"])
        self.assertEqual(r["Cache-Control"], "private, no-store")
        cuerpo = b"".join(r.streaming_content)
        self.assertTrue(cuerpo.startswith(b"%PDF"))
        lector = PdfReader(BytesIO(cuerpo))
        self.assertGreaterEqual(len(lector.pages), 1)
        texto = texto_pdf(cuerpo)
        for esperado in (self.e1.codigo, "CertiTrack 360 · CERTICOM", "Cliente Demo", "noviembre de 2026", "TDR-2026-007",
                         "Operación mensual del año niño", "Exportado por", "Página 1", "Código", "Fecha de recepción"):
            self.assertIn(esperado, texto)

    def test_pdf_con_textos_largos_ajusta_linea_y_pagina(self):
        largo = "palabra " * 600
        self.e1.datos = {"c_periodo": largo, "c_nivel": "3" * 300}
        self.e1.save()
        contenido = servicios.exportar(self.e1, self.j1, "pdf")
        cuerpo = contenido_de(contenido)
        lector = PdfReader(BytesIO(cuerpo))
        self.assertGreater(len(lector.pages), 1)
        self.assertIn("Página 2", texto_pdf(cuerpo))
        self.assertIn("palabra palabra", texto_pdf(cuerpo))

    def test_documento_tabular_reutilizable(self):
        bytes_ = pdf.documento_tabular(
            "Reporte de prueba ñandú", "Subtítulo con tildes áéíóú",
            [{"titulo": "Totales", "encabezados": ["Cliente", "Entregados"], "filas": [["Ñ & <b>", 3], ["Otro", 5]]},
             {"titulo": "Pares", "filas": [("Campo", "Valor <tag>")]}, {"titulo": "Vacía", "filas": []}],
            "Pie de prueba",
        )
        texto = texto_pdf(bytes_)
        for esperado in ("Reporte de prueba ñandú", "áéíóú", "Totales", "Ñ & <b>", "Valor <tag>", "Sin datos.", "Pie de prueba",
                         "Página 1"):
            self.assertIn(esperado, texto)


class ExcelTests(BaseExportacion):
    def test_criterios_2_y_5_excel_estandar_se_abre_con_openpyxl_y_trae_los_valores(self):
        self.client.force_login(self.j1)
        r = self.client.post(self.url_excel)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], servicios.TIPOS_MIME["excel"])
        self.assertIn(f"{self.e1.codigo}_v1.xlsx", r["Content-Disposition"])
        libro = load_workbook(BytesIO(b"".join(r.streaming_content)))
        hoja = libro.active
        self.assertEqual([hoja["A1"].value, hoja["B1"].value], ["Campo", "Valor"])
        self.assertTrue(hoja["A1"].font.bold and hoja["B1"].font.bold)
        filas = {}
        for fila in hoja.iter_rows(min_row=2):
            filas.setdefault(fila[0].value, fila[1].value)  # la plantilla de prueba tiene un campo «Periodo» más
        self.assertEqual(filas["Código"], self.e1.codigo)
        self.assertEqual(filas["Cliente"], "Cliente Demo")
        self.assertEqual(filas["Periodo"], "noviembre de 2026")
        self.assertEqual(filas["Plazo"], "20/11/2026")
        self.assertEqual(filas["Fecha de recepción"], "03/11/2026")
        self.assertEqual(filas["ID-TDR"], "TDR-2026-007")
        self.assertEqual(filas["Periodo"], "noviembre de 2026")
        self.assertEqual(filas["Nivel"], "3")
        self.assertGreater(hoja.column_dimensions["B"].width, 20)

    def test_un_valor_que_empieza_con_igual_no_se_convierte_en_formula(self):
        self.e1.datos = {"c_periodo": "=1+1", "c_nivel": "3"}
        self.e1.save()
        a = servicios.exportar(self.e1, self.j1, "excel")
        hoja = load_workbook(BytesIO(contenido_de(a))).active
        valores = {f[0].value: f[1] for f in hoja.iter_rows(min_row=2)}
        self.assertEqual(valores["Periodo"].value, "=1+1")
        self.assertEqual(valores["Periodo"].data_type, "s")

    def test_con_formato_xlsx_enlazado_se_rellenan_los_marcadores(self):
        """D11: marcadores de §7.8 y de los campos de la plantilla; uno desconocido queda vacío y se informa."""
        self.formato_xlsx({
            "A1": "Informe de {{cliente}} — {{periodo}}", "A2": "{{codigo}}", "B2": "TDR: {{id_tdr}} / {{plazo}}",
            "A3": "{{c_periodo}}", "B3": "{{junior}} y {{senior}}", "A4": "{{titulo}} {{contrato}} {{linea_servicio}}",
            "A5": "{{fecha_recepcion}} {{ }}","A6": "Sin marcador", "A7": "{{ inexistente }}", "A8": 42,
        })
        a = servicios.exportar(self.e1, self.s1, "excel")
        hoja = load_workbook(BytesIO(contenido_de(a))).active
        self.assertEqual(hoja["A1"].value, "Informe de Cliente Demo — noviembre de 2026")
        self.assertEqual(hoja["A2"].value, self.e1.codigo)
        self.assertEqual(hoja["B2"].value, "TDR: TDR-2026-007 / 20/11/2026")
        self.assertEqual(hoja["A3"].value, PERIODO)
        self.assertEqual(hoja["B3"].value, f"{self.j1.nombre} y {self.s1.nombre}")
        self.assertTrue(hoja["A4"].value.startswith("E1 C1"))
        self.assertEqual(hoja["A6"].value, "Sin marcador")
        self.assertIn(hoja["A7"].value, ("", None))
        self.assertEqual(hoja["A8"].value, 42)
        self.assertEqual(a.comentario, "Exportación a Excel; marcadores sin dato: inexistente")
        self.assertEqual(hoja.max_row, 8)  # no es la hoja estándar de dos columnas

    def test_sin_formato_vigente_xlsx_usa_la_hoja_estandar(self):
        doc = self.formato_xlsx({"A1": "{{cliente}}"})
        # Una versión vigente que no es .xlsx (p. ej. PDF) no sirve de formato para el Excel.
        VersionDocumento.objects.filter(documento=doc).update(vigente=False)
        VersionDocumento.objects.create(documento=doc, numero=2, archivo=ContentFile(b"%PDF-1.4 x", name="f.pdf"),
                                        nombre_original="f.pdf", vigente=True, subido_por=self.gerente)
        hoja = load_workbook(BytesIO(contenido_de(servicios.exportar(self.e1, self.s1, "excel")))).active
        self.assertEqual(hoja["A1"].value, "Campo")

    def test_formato_corrupto_cae_al_estandar_y_lo_informa(self):
        doc = self.formato_xlsx({"A1": "x"})
        v = doc.versiones.get()
        v.archivo.save("roto.xlsx", ContentFile(b"esto no es un xlsx"), save=True)
        a = servicios.exportar(self.e1, self.s1, "excel")
        self.assertIn("no se pudo abrir", a.comentario)
        self.assertEqual(load_workbook(BytesIO(contenido_de(a))).active["A1"].value, "Campo")

    def test_excel_generar_sin_marcadores_desconocidos(self):
        contenido, desconocidos, uso = excel.generar([("a", "A", "1")])
        self.assertEqual((desconocidos, uso), ([], False))
        self.assertEqual(load_workbook(BytesIO(contenido)).active["B2"].value, "1")


class VersionadoEHistorialTests(BaseExportacion):
    def test_criterio_4_cada_exportacion_es_una_version_nueva_con_usuario_fecha_y_hora(self):
        """HU-27 criterio 4: registra usuario, fecha y hora y guarda el archivo como versión nueva del entregable."""
        self.client.force_login(self.j1)
        self.client.post(self.url_pdf)
        self.client.force_login(self.s1)
        self.client.post(self.url_excel)
        self.client.post(self.url_pdf)
        lista = list(Adjunto.objects.filter(entregable=self.e1, tipo=TipoAdjunto.EXPORTACION).order_by("version"))
        self.assertEqual([a.version for a in lista], [1, 2, 3])
        self.assertEqual([a.nombre_original for a in lista],
                         [f"{self.e1.codigo}_v1.pdf", f"{self.e1.codigo}_v2.xlsx", f"{self.e1.codigo}_v3.pdf"])
        self.assertEqual([a.subido_por for a in lista], [self.j1, self.s1, self.s1])
        self.assertEqual([a.comentario for a in lista], ["Exportación a PDF", "Exportación a Excel", "Exportación a PDF"])
        self.assertEqual(len({a.archivo.name for a in lista}), 3)  # nunca se sobrescribe
        for a in lista:
            self.assertTrue(contenido_de(a))
        historial = list(HistorialEstado.objects.filter(entregable=self.e1, detalle__startswith="Exportó").order_by("id"))
        self.assertEqual([h.usuario for h in historial], [self.j1, self.s1, self.s1])
        self.assertIn("Exportó el entregable a PDF (v1", historial[0].detalle)
        self.assertIn("Exportó el entregable a Excel (v2", historial[1].detalle)
        self.assertTrue(all(h.fecha for h in historial))
        self.assertEqual(self.e1.estado, historial[0].estado_nuevo)  # no cambia de estado

    def test_la_seccion_lista_las_exportaciones_anteriores_con_descarga(self):
        self.client.force_login(self.s1)
        self.client.post(self.url_pdf)
        r = self.client.get(reverse("entregable_detalle", args=[self.e1.pk]))
        a = Adjunto.objects.get(tipo=TipoAdjunto.EXPORTACION)
        self.assertContains(r, "Exportaciones anteriores")
        self.assertContains(r, reverse("adjunto_descargar", args=[a.pk]))
        self.assertContains(r, "v1")
        self.assertContains(r, self.s1.nombre)
        # Se descarga con la vista existente.
        d = self.client.get(reverse("adjunto_descargar", args=[a.pk]))
        self.assertEqual(d.status_code, 200)
        self.assertTrue(b"".join(d.streaming_content).startswith(b"%PDF"))
        # Quien no ve el entregable no la descarga.
        self.client.force_login(self.j2)
        self.assertEqual(self.client.get(reverse("adjunto_descargar", args=[a.pk])).status_code, 404)

    def test_la_exportacion_es_atomica_si_falla_el_guardado(self):
        from unittest import mock
        with mock.patch("apps.exportacion.servicios.adjuntos.crear_adjunto", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                servicios.exportar(self.e1, self.j1, "pdf")
        self.assertEqual(Adjunto.objects.filter(tipo=TipoAdjunto.EXPORTACION).count(), 0)

    def test_nombres_con_enie_en_el_pdf_y_en_el_nombre_del_archivo(self):
        otro = Cliente.objects.create(nombre="Ñandú S.A.", sector="BANCA")
        contrato = Contrato.objects.create(cliente=otro, numero_contrato="C9", fecha_inicio=datetime.date(2026, 1, 1),
                                           fecha_fin=datetime.date(2027, 1, 1), senior_responsable=self.s1)
        contrato.juniors.set([self.j1])
        e = self.nuevo(contrato, self.j1, self.s1, "Con ñ")
        e.id_tdr, e.fecha_recepcion = "T-1", datetime.date(2026, 11, 1)
        e.save()
        a = servicios.exportar(e, self.s1, "pdf")
        self.assertIn("Ñandú S.A.", texto_pdf(contenido_de(a)))
        self.assertTrue(a.nombre_original.startswith(e.codigo))
