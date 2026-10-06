import re
from unittest import TestCase

from apps.entregables import demo_archivos


class PdfMinimoTests(TestCase):
    def setUp(self):
        self.pdf = demo_archivos.pdf_minimo("Informe (ficticio) \\ prueba", ["Línea con tilde: informe técnico", "Otra línea"])

    def test_tiene_cabecera_y_cierre(self):
        self.assertTrue(self.pdf.startswith(b"%PDF-1.4\n"))
        self.assertTrue(self.pdf.rstrip().endswith(b"%%EOF"))

    def test_la_tabla_de_referencias_apunta_a_cada_objeto(self):
        inicio = int(re.search(rb"startxref\n(\d+)\n", self.pdf).group(1))
        self.assertTrue(self.pdf[inicio:].startswith(b"xref\n0 6\n"))
        entradas = re.findall(rb"(\d{10}) 00000 n \n", self.pdf)
        self.assertEqual(len(entradas), 5)
        for numero, posicion in enumerate(entradas, start=1):
            self.assertTrue(self.pdf[int(posicion):].startswith(b"%d 0 obj\n" % numero), numero)

    def test_la_longitud_del_flujo_es_correcta(self):
        longitud = int(re.search(rb"/Length (\d+) >>", self.pdf).group(1))
        flujo = self.pdf.split(b"stream\n", 1)[1].split(b"\nendstream", 1)[0]
        self.assertEqual(len(flujo), longitud)

    def test_escapa_parentesis_y_barras(self):
        self.assertIn(b"(Informe \\(ficticio\\) \\\\ prueba) Tj", self.pdf)

    def test_los_acentos_van_en_cp1252(self):
        self.assertIn("técnico".encode("cp1252"), self.pdf)


class ContenidoDemoTests(TestCase):
    def test_pdf_y_txt_llevan_el_aviso_de_dato_ficticio(self):
        self.assertIn(b"ficticio", demo_archivos.contenido_demo("pdf", "T", "D"))
        self.assertIn("ficticio".encode(), demo_archivos.contenido_demo("txt", "T", "D"))
        self.assertTrue(demo_archivos.contenido_demo("pdf", "T", "D").startswith(b"%PDF"))
