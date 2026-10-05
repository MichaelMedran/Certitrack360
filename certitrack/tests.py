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
