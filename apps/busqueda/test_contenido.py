"""Búsqueda dentro del contenido de los adjuntos: lectura del texto por formato, visibilidad y relectura."""
import io
import zipfile
from io import StringIO

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse

from apps.busqueda.servicios import buscar
from apps.entregables import adjuntos
from apps.entregables.models import Adjunto
from apps.entregables.tests import Base
from apps.entregables.texto import MAX_CARACTERES, extraer_texto, fragmento
from apps.entregables.tipos import TipoAdjunto


def pdf(texto):
    from reportlab.pdfgen import canvas

    salida = io.BytesIO()
    hoja = canvas.Canvas(salida)
    hoja.drawString(72, 720, texto)
    hoja.save()
    return salida.getvalue()


def docx(texto):
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as paquete:
        paquete.writestr("word/document.xml", f"<w:document><w:body><w:p><w:r><w:t>{texto}</w:t></w:r></w:p></w:body></w:document>")
    return salida.getvalue()


def pptx(texto):
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as paquete:
        paquete.writestr("ppt/slides/slide1.xml", f"<p:sld><a:p><a:r><a:t>{texto}</a:t></a:r></a:p></p:sld>")
    return salida.getvalue()


def xlsx(*valores):
    from openpyxl import Workbook

    libro = Workbook()
    libro.active.title = "Movimientos"
    libro.active.append(list(valores))
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


class LecturaDeTextoTests(Base):
    def test_lee_cada_formato_admitido(self):
        casos = {
            "informe.pdf": pdf("Custodia de expedientes"),
            "carta.docx": docx("Custodia de expedientes &amp; anexos"),
            "resumen.pptx": pptx("Custodia de expedientes"),
            "cajas.xlsx": xlsx("Custodia de expedientes", 1250),
            "nota.txt": "Custodia de expedientes".encode(),
            "NOTA.TXT": "Custodia de expedientes".encode("latin-1"),
        }
        for nombre, contenido in casos.items():
            with self.subTest(nombre=nombre):
                self.assertIn("Custodia de expedientes", extraer_texto(ContentFile(contenido, name=nombre)))
        self.assertIn("& anexos", extraer_texto(ContentFile(casos["carta.docx"], name="carta.docx")))
        self.assertIn("1250", extraer_texto(ContentFile(casos["cajas.xlsx"], name="cajas.xlsx")))

    def test_lo_que_no_se_puede_leer_queda_sin_texto_y_no_falla(self):
        for nombre, contenido in (("foto.png", b"\x89PNG"), ("roto.pdf", b"esto no es un pdf"), ("roto.docx", b"nada"),
                                  ("roto.xlsx", b"nada"), ("sin_extension", b"hola")):
            with self.subTest(nombre=nombre):
                self.assertEqual(extraer_texto(ContentFile(contenido, name=nombre)), "")

    def test_el_texto_se_acota_y_no_lleva_caracteres_nulos(self):
        texto = extraer_texto(ContentFile(("a\x00b  c\n\n\n" * MAX_CARACTERES).encode(), name="largo.txt"))
        self.assertEqual(len(texto), MAX_CARACTERES)
        self.assertNotIn("\x00", texto)
        self.assertTrue(texto.startswith("a b c\na b c"))

    def test_leer_el_texto_no_mueve_el_archivo(self):
        archivo = ContentFile(b"hola mundo", name="nota.txt")
        archivo.seek(3)
        extraer_texto(archivo)
        self.assertEqual(archivo.tell(), 3)

    def test_fragmento_rodea_la_palabra_sin_distinguir_tildes(self):
        texto = "x" * 200 + " El número de caja 4471 no coincide " + "y" * 200
        trozo = fragmento(texto, ["NUMERO"])
        self.assertIn("número de caja 4471", trozo)
        self.assertTrue(trozo.startswith("… ") and trozo.endswith(" …"))
        self.assertEqual(fragmento(texto, ["inexistente"]), "")


class BusquedaEnContenidoTests(Base):
    def subir(self, entregable, usuario, nombre, contenido, tipo=TipoAdjunto.EVIDENCIA):
        return adjuntos.subir(entregable, usuario, SimpleUploadedFile(nombre, contenido), tipo)

    def test_al_subir_se_guarda_el_texto_y_el_buscador_lo_encuentra(self):
        adjunto = self.subir(self.e1, self.j1, "evidencia.txt", "Acta de traslado de la caja 4471 al almacén".encode())
        self.assertIn("caja 4471", adjunto.texto)
        res = buscar(self.j1, {"q": "ALMACEN 4471"})
        self.assertEqual(res["adjuntos"], [adjunto])
        self.assertIn("caja 4471 al almacén", res["adjuntos"][0].fragmento)

        self.client.force_login(self.j1)
        html = self.client.get(reverse("buscar"), {"q": "almacen"}).content.decode()
        self.assertIn("En el contenido:", html)
        self.assertIn("caja 4471", html)

    def test_una_coincidencia_solo_en_el_nombre_no_muestra_fragmento(self):
        adjunto = self.subir(self.e1, self.j1, "traslado.txt", b"sin relacion")
        res = buscar(self.j1, {"q": "traslado"})
        self.assertEqual([(a.pk, a.fragmento) for a in res["adjuntos"]], [(adjunto.pk, "")])

    def test_el_contenido_respeta_la_visibilidad_por_rol(self):
        self.subir(self.e1, self.j1, "evidencia.txt", b"clausula reservada zafiro")
        self.assertEqual(len(buscar(self.j1, {"q": "zafiro"})["adjuntos"]), 1)
        self.assertEqual(len(buscar(self.gerente, {"q": "zafiro"})["adjuntos"]), 1)
        self.assertEqual(buscar(self.j2, {"q": "zafiro"})["adjuntos"], [])
        self.assertEqual(buscar(self.j2, {"q": "zafiro"})["total_resultados"], 0)

    def test_el_comando_lee_los_adjuntos_que_ya_existian(self):
        adjunto = self.subir(self.e1, self.j1, "antiguo.txt", b"penalidad por retraso")
        Adjunto.objects.filter(pk=adjunto.pk).update(texto="")
        perdido = Adjunto.objects.create(entregable=self.e1, archivo="adjuntos/no_existe.txt", nombre_original="no_existe.txt",
                                         tipo=TipoAdjunto.EVIDENCIA, version=9, subido_por=self.j1)
        self.assertEqual(buscar(self.j1, {"q": "penalidad"})["adjuntos"], [])
        salida = StringIO()
        call_command("indexar_adjuntos", stdout=salida)
        self.assertIn("Adjuntos revisados: 2. Con texto para buscar: 1.", salida.getvalue())
        self.assertEqual(buscar(self.j1, {"q": "penalidad"})["adjuntos"], [adjunto])
        perdido.refresh_from_db()
        self.assertEqual(perdido.texto, "")
