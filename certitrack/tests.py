"""Pruebas transversales de privacidad y seguridad (SDD RNF-01, RNF-04, §15)."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

RAIZ = Path(settings.BASE_DIR)
URL_EXTERNA = re.compile(r"(?:https?:)?//[\w.-]+\.[a-z]{2,}", re.I)


class SinRecursosExternosTests(SimpleTestCase):
    """RNF-01: sin CDNs, fuentes ni analíticas; todo se sirve desde static/."""

    def test_las_plantillas_no_enlazan_a_ningun_sitio_externo(self):
        for ruta in (RAIZ / "templates").rglob("*.html"):
            with self.subTest(plantilla=ruta.relative_to(RAIZ).as_posix()):
                self.assertEqual(URL_EXTERNA.findall(ruta.read_text(encoding="utf-8")), [])

    def test_el_css_propio_no_importa_nada_externo(self):
        for ruta in (RAIZ / "static" / "css").rglob("*.css"):
            with self.subTest(css=ruta.name):
                self.assertEqual(URL_EXTERNA.findall(ruta.read_text(encoding="utf-8")), [])

    def test_los_wireframes_tampoco(self):
        for ruta in (RAIZ / "docs" / "wireframes").glob("*.*"):
            with self.subTest(archivo=ruta.name):
                self.assertEqual(URL_EXTERNA.findall(ruta.read_text(encoding="utf-8")), [])

    def test_las_bibliotecas_estan_copiadas_en_static(self):
        for nombre in ("htmx.min.js", "Sortable.min.js", "fullcalendar.min.js", "fullcalendar-es.min.js"):
            self.assertTrue((RAIZ / "static" / "js" / nombre).exists(), nombre)

    def test_no_hay_scripts_remotos_en_la_base(self):
        base = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")
        for etiqueta in re.findall(r"<(?:script|link)[^>]+>", base):
            self.assertNotRegex(etiqueta, r"(?:src|href)=\"(?:https?:)?//")


class WireframesTests(SimpleTestCase):
    """H0.5: los wireframes de todas las pantallas del SDD (§13.2) existen y están bien formados."""

    PANTALLAS = ["login", "inicio", "tablero", "lista", "entregable", "nuevo", "calendario", "notificaciones",
                 "consolidado", "gestion", "asistente", "administracion"]
    VACIAS = {"meta", "link", "br", "hr", "img", "input"}

    def paginas(self):
        return [RAIZ / "docs" / "wireframes" / f"{n}.html" for n in ["index", *self.PANTALLAS]]

    def revisar(self, ruta):
        from html.parser import HTMLParser

        pila, errores, enlaces = [], [], []

        class Lector(HTMLParser):
            def handle_starttag(inner, tag, attrs):
                if tag not in self.VACIAS:
                    pila.append(tag)
                enlaces.extend(v for k, v in attrs if k in ("href", "src") and v)

            def handle_endtag(inner, tag):
                if tag in self.VACIAS:
                    return
                if not pila or pila[-1] != tag:
                    errores.append(f"</{tag}> inesperado")
                else:
                    pila.pop()

        lector = Lector()
        lector.feed(ruta.read_text(encoding="utf-8"))
        return errores + [f"sin cerrar: {t}" for t in pila], enlaces

    def test_existen_el_indice_y_las_doce_pantallas(self):
        for ruta in self.paginas():
            self.assertTrue(ruta.exists(), ruta.name)
        self.assertTrue((RAIZ / "docs" / "wireframes" / "wf.css").exists())

    def test_el_html_esta_bien_formado_y_los_enlaces_funcionan(self):
        for ruta in self.paginas():
            with self.subTest(pagina=ruta.name):
                errores, enlaces = self.revisar(ruta)
                self.assertEqual(errores, [])
                for enlace in enlaces:
                    self.assertTrue((ruta.parent / enlace).exists(), f"enlace roto: {enlace}")

    def test_el_indice_enlaza_a_todas_las_pantallas_y_las_lista_en_el_registro_de_aprobacion(self):
        indice = (RAIZ / "docs" / "wireframes" / "index.html").read_text(encoding="utf-8")
        for nombre in self.PANTALLAS:
            self.assertIn(f'href="{nombre}.html"', indice)
        self.assertEqual(indice.count("<td>&nbsp;</td><td>&nbsp;</td>"), len(self.PANTALLAS))

    def test_son_de_baja_fidelidad_sin_colores_ni_scripts(self):
        css = (RAIZ / "docs" / "wireframes" / "wf.css").read_text(encoding="utf-8")
        colores = re.findall(r"#([0-9a-fA-F]{3,6})\b", css)
        self.assertTrue(colores)  # sí usa colores, pero todos son grises
        self.assertEqual([c for c in colores if not self.es_gris(c)], [])
        for ruta in self.paginas():
            self.assertNotIn("<script", ruta.read_text(encoding="utf-8").lower())

    @staticmethod
    def es_gris(hexa):
        if len(hexa) == 3:
            hexa = "".join(ch * 2 for ch in hexa)
        return hexa[0:2].lower() == hexa[2:4].lower() == hexa[4:6].lower()


class ConfiguracionSeguraTests(SimpleTestCase):
    def test_los_archivos_subidos_no_tienen_url_publica(self):
        self.assertIsNone(settings.MEDIA_URL)

    def test_los_medios_viven_fuera_del_codigo_y_no_se_versionan(self):
        gitignore = (RAIZ / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("media/", gitignore)
        self.assertIn(".env", gitignore)
        self.assertIn("db.sqlite3", gitignore)

    def test_no_hay_secretos_en_el_ejemplo_de_entorno(self):
        ejemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
        self.assertIn("DJANGO_SECRET_KEY=", ejemplo)
        self.assertNotRegex(ejemplo, r"(?i)(password|secret_key)=(?!cambie)\S")

    def test_las_cookies_de_sesion_y_csrf_comparten_la_misma_politica(self):
        self.assertEqual(settings.SESSION_COOKIE_SECURE, settings.CSRF_COOKIE_SECURE)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
