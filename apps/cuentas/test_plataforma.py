"""Plataforma independiente (SDD del Sprint 3, §7.12, RF-51, RNF-16, HU-09): bloqueo de ingreso, política de contenido,
ausencia de orígenes externos y servidor de producción."""
import datetime
import http.client
import io
import re
import threading
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.cuentas import bloqueo
from apps.cuentas.middleware import politica_de_contenido
from apps.cuentas.models import IntentoIngreso, Usuario
from apps.entregables import test_entregas as te

RAIZ = Path(settings.BASE_DIR)
CLAVE = "clave-segura-123"


def intentar(client, usuario, clave, url="login", ip="10.0.0.5"):
    return client.post(reverse(url), {"username": usuario, "password": clave}, REMOTE_ADDR=ip)


class BloqueoDeIngresoTests(TestCase):
    def setUp(self):
        self.ana = Usuario.objects.create_user("ana", password=CLAVE, rol="JUNIOR")
        Usuario.objects.create_user("luis", password=CLAVE, rol="JUNIOR")
        self.client = Client()

    def fallar(self, veces, usuario="ana", ip="10.0.0.5"):
        for _ in range(veces):
            r = intentar(self.client, usuario, "equivocada", ip=ip)
            self.assertEqual(r.status_code, 200)

    def test_los_cinco_primeros_fallos_se_permiten_y_el_sexto_intento_se_bloquea(self):
        self.fallar(5)
        r = intentar(self.client, "ana", "equivocada")
        self.assertEqual(r.status_code, 429)
        self.assertContains(r, "Demasiados intentos fallidos", status_code=429)

    def test_con_el_bloqueo_activo_ni_la_contrasena_correcta_entra(self):
        self.fallar(5)
        r = intentar(self.client, "ana", CLAVE)
        self.assertEqual(r.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(reverse("inicio")).status_code, 302)

    def test_sin_llegar_al_limite_la_contrasena_correcta_entra(self):
        self.fallar(4)
        r = intentar(self.client, "ana", CLAVE)
        self.assertRedirects(r, reverse("inicio"), fetch_redirect_response=False)

    def test_un_ingreso_acertado_reinicia_la_cuenta(self):
        self.fallar(4)
        intentar(self.client, "ana", CLAVE)
        self.client.logout()
        self.fallar(4)
        self.assertEqual(intentar(self.client, "ana", CLAVE).status_code, 302)

    def test_el_bloqueo_es_por_usuario_y_por_direccion(self):
        self.fallar(5)
        self.assertEqual(intentar(self.client, "luis", CLAVE).status_code, 302)  # otro usuario, misma dirección
        self.client.logout()
        self.assertEqual(intentar(self.client, "ana", CLAVE, ip="10.0.0.99").status_code, 302)  # otra dirección

    def test_los_intentos_bloqueados_no_alargan_el_bloqueo(self):
        self.fallar(5)
        for _ in range(3):
            intentar(self.client, "ana", "equivocada")
        self.assertEqual(IntentoIngreso.objects.filter(usuario_texto="ana", exitoso=False).count(), 5)

    def test_el_bloqueo_termina_a_los_quince_minutos(self):
        self.fallar(5)
        IntentoIngreso.objects.update(fecha=timezone.now() - datetime.timedelta(minutes=settings.LOGIN_BLOQUEO_MINUTOS + 1))
        self.assertEqual(intentar(self.client, "ana", CLAVE).status_code, 302)

    def test_el_aviso_dice_hasta_que_hora_dura(self):
        self.fallar(5)
        hasta = bloqueo.bloqueado_hasta("ana", "10.0.0.5")
        r = intentar(self.client, "ana", CLAVE)
        self.assertContains(r, f"hasta las {timezone.localtime(hasta):%H:%M}", status_code=429)

    @override_settings(LOGIN_MAX_INTENTOS=2)
    def test_el_limite_se_configura(self):
        self.fallar(2)
        self.assertEqual(intentar(self.client, "ana", "equivocada").status_code, 429)

    def test_ignora_mayusculas_y_espacios_en_el_nombre_escrito(self):
        for variante in ("ANA", " ana ", "Ana", "aNa", "ana"):
            intentar(self.client, variante, "equivocada")
        self.assertEqual(intentar(self.client, "ana", CLAVE).status_code, 429)

    def test_el_panel_tecnico_tambien_queda_bloqueado(self):
        Usuario.objects.create_user("jefe", password=CLAVE, rol="ADMIN")
        for _ in range(5):
            intentar(self.client, "jefe", "equivocada", url="admin:login")
        r = intentar(self.client, "jefe", CLAVE, url="admin:login")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotEqual(r.status_code, 302)

    def test_los_intentos_viejos_se_depuran(self):
        IntentoIngreso.objects.create(usuario_texto="x", ip="1.1.1.1")
        IntentoIngreso.objects.update(fecha=timezone.now() - datetime.timedelta(days=bloqueo.CONSERVAR_DIAS + 1))
        bloqueo.registrar("ana", "10.0.0.5", exitoso=False)
        self.assertFalse(IntentoIngreso.objects.filter(usuario_texto="x").exists())

    def test_sin_request_no_se_aplica_el_bloqueo(self):
        from django.contrib.auth import authenticate

        for _ in range(7):
            bloqueo.registrar("ana", "", exitoso=False)
        self.assertEqual(authenticate(username="ana", password=CLAVE), self.ana)


class PoliticaDeContenidoTests(TestCase):
    def test_toda_respuesta_lleva_la_politica_y_ninguna_cabecera_de_origen_externo(self):
        r = self.client.get(reverse("login"))
        csp = r["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("script-src 'self'", csp)
        self.assertIn("form-action 'self'", csp)
        self.assertIn("connect-src 'self'", csp)
        self.assertNotRegex(csp, r"https?://")
        self.assertNotIn("*", csp)
        self.assertEqual(r["Referrer-Policy"], "same-origin")

    def test_tambien_en_paginas_autenticadas_y_en_errores(self):
        usuario = Usuario.objects.create_user("ana", password=CLAVE, rol="GERENTE")
        self.client.force_login(usuario)
        for url in ("inicio", "calendario", "tablero"):
            self.assertIn("Content-Security-Policy", self.client.get(reverse(url)), url)
        self.assertIn("Content-Security-Policy", self.client.get("/no-existe/"))

    @override_settings(FILEDOC_ORIGEN="https://filedoc.certicom.local")
    def test_filedoc_es_el_unico_origen_externo_y_solo_para_enviar_y_consultar(self):
        csp = politica_de_contenido()
        self.assertEqual(re.findall(r"https?://[^\s;]+", csp), ["https://filedoc.certicom.local"] * 2)
        self.assertIn("connect-src 'self' https://filedoc.certicom.local", csp)
        self.assertIn("form-action 'self' https://filedoc.certicom.local", csp)
        self.assertIn("default-src 'self';", csp)

    def test_sin_filedoc_configurado_no_hay_ningun_origen_externo(self):
        self.assertEqual(settings.FILEDOC_ORIGEN, "")
        self.assertNotRegex(politica_de_contenido(), r"https?://")

    def test_filedoc_url_invalida_se_rechaza_al_configurar(self):
        import subprocess
        import sys

        proceso = subprocess.run(
            [sys.executable, "-c", "import certitrack.settings"], cwd=RAIZ, capture_output=True, text=True,
            env={**__import__("os").environ, "FILEDOC_URL": "filedoc.local"})
        self.assertNotEqual(proceso.returncode, 0)
        self.assertIn("FILEDOC_URL", proceso.stderr)

    def test_no_queda_ningun_script_en_linea_ni_manejador_de_eventos(self):
        for ruta in (RAIZ / "templates").rglob("*.html"):
            texto = ruta.read_text(encoding="utf-8")
            with self.subTest(plantilla=ruta.relative_to(RAIZ).as_posix()):
                self.assertEqual(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", texto), [])
                self.assertEqual(re.findall(r"\son[a-z]+\s*=\s*[\"']", texto, re.I), [])
                self.assertNotIn("javascript:", texto.lower())


class SinOrigenesExternosTests(SimpleTestCase):
    """RNF-16: ninguna plantilla ni estático apunta a otro origen que el propio servidor."""

    EXTERNO = re.compile(r"(?:https?:)?//[\w-]+(?:\.[\w-]+)+", re.I)
    # Texto que aparece en las bibliotecas copiadas y que no carga nada: encabezados de licencia y el espacio de nombres SVG.
    INOFENSIVOS = {"//fullcalendar.io", "//github.com", "//www.w3.org"}

    def hallazgos(self, ruta):
        encontrados = {m.group(0).split(":")[-1] for m in self.EXTERNO.finditer(ruta.read_text(encoding="utf-8"))}
        return {h for h in encontrados if h not in self.INOFENSIVOS}

    def test_plantillas_sin_origenes_externos_ni_en_atributos_de_carga_o_envio(self):
        for ruta in (RAIZ / "templates").rglob("*.html"):
            texto = ruta.read_text(encoding="utf-8")
            with self.subTest(plantilla=ruta.relative_to(RAIZ).as_posix()):
                self.assertEqual(self.hallazgos(ruta), set())
                self.assertEqual(re.findall(r"(?:src|href|action|formaction|srcset|data|poster)\s*=\s*[\"'](?:https?:)?//", texto, re.I), [])
                self.assertEqual(re.findall(r"@import|url\(\s*[\"']?(?:https?:)?//", texto, re.I), [])

    def test_estaticos_sin_origenes_externos(self):
        for ruta in sorted((RAIZ / "static").rglob("*")):
            if ruta.suffix not in (".css", ".js", ".html", ".svg"):
                continue
            with self.subTest(estatico=ruta.relative_to(RAIZ).as_posix()):
                self.assertEqual(self.hallazgos(ruta), set())

    def test_los_estaticos_propios_no_hacen_peticiones_a_otros_sitios(self):
        propios = [r for r in (RAIZ / "static" / "js").glob("*.js") if ".min." not in r.name]
        self.assertTrue(propios)
        for ruta in propios:
            with self.subTest(script=ruta.name):
                self.assertNotRegex(ruta.read_text(encoding="utf-8"), r"https?://|\bWebSocket\b|\bnew EventSource\b|sendBeacon")

    def test_el_calendario_vive_en_un_estatico(self):
        self.assertTrue((RAIZ / "static" / "js" / "calendario.js").exists())


class EnlaceFiledocTests(te.EntregasBase):
    def setUp(self):
        self.e = self.aprobado()
        self.url = reverse("entregable_entregar", args=[self.e.pk])
        self.client.force_login(self.s1)

    def test_sin_filedoc_configurado_no_hay_enlace(self):
        self.assertNotContains(self.client.get(self.url), "Abrir Filedoc")

    @override_settings(FILEDOC_URL="https://filedoc.certicom.local/mesa")
    def test_con_filedoc_el_enlace_esta_y_solo_se_ve_con_el_medio_filedoc(self):
        r = self.client.get(self.url)
        self.assertContains(r, 'href="https://filedoc.certicom.local/mesa" target="_blank" rel="noopener noreferrer">Abrir Filedoc</a>')
        self.assertContains(r, '<p id="enlace-filedoc" hidden>')
        self.assertContains(r, "js/entregar.js")
        r = self.client.post(self.url, {"medio": "FILEDOC"})  # con errores de validación: vuelve a mostrar el formulario
        self.assertContains(r, '<p id="enlace-filedoc">')


class ServidorDeProduccionTests(TestCase):
    def test_servir_arranca_waitress_con_la_configuracion_y_los_estaticos(self):
        servidor = mock.Mock()
        with mock.patch("waitress.create_server", return_value=servidor) as crear, \
                mock.patch("apps.cuentas.management.commands.servir.call_command") as collectstatic:
            salida = io.StringIO()
            call_command("servir", "--puerto=8123", "--hilos=3", "--host=127.0.0.1", stdout=salida)
        collectstatic.assert_called_once_with("collectstatic", interactive=False, verbosity=0)
        args, kwargs = crear.call_args
        self.assertTrue(callable(args[0]))
        self.assertEqual((kwargs["host"], kwargs["port"], kwargs["threads"]), ("127.0.0.1", 8123, 3))
        servidor.run.assert_called_once_with()
        servidor.close.assert_called_once_with()
        self.assertIn("escuchando en http://127.0.0.1:8123/", salida.getvalue())

    def test_servir_usa_los_valores_de_la_configuracion_por_defecto(self):
        with mock.patch("waitress.create_server", return_value=mock.Mock()) as crear:
            call_command("servir", "--sin-estaticos", stdout=io.StringIO())
        self.assertEqual((crear.call_args.kwargs["port"], crear.call_args.kwargs["threads"]),
                         (settings.SERVIDOR_PUERTO, settings.SERVIDOR_HILOS))

    def test_ctrl_c_detiene_el_servidor_sin_error(self):
        servidor = mock.Mock(run=mock.Mock(side_effect=KeyboardInterrupt))
        with mock.patch("waitress.create_server", return_value=servidor):
            salida = io.StringIO()
            call_command("servir", "--sin-estaticos", stdout=salida)
        servidor.close.assert_called_once_with()
        self.assertIn("Servidor detenido", salida.getvalue())

    def test_waitress_atiende_la_aplicacion_real_sin_dejar_nada_colgado(self):
        """Arranque real en un puerto libre: responde, trae la política de contenido y se cierra."""
        from waitress import create_server

        from certitrack.wsgi import application

        servidor = create_server(application, host="127.0.0.1", port=0, threads=2)
        hilo = threading.Thread(target=servidor.run, daemon=True)
        hilo.start()
        try:
            conexion = http.client.HTTPConnection("127.0.0.1", servidor.effective_port, timeout=10)
            conexion.request("GET", "/login/")
            r = conexion.getresponse()
            cuerpo = r.read().decode()
            self.assertEqual(r.status, 200)
            self.assertIn("default-src 'self'", r.getheader("Content-Security-Policy"))
            self.assertIn("CertiTrack 360", cuerpo)
            conexion.request("GET", "/static/js/certitrack.js")  # WhiteNoise sirve los estáticos
            estatico = conexion.getresponse()
            estatico.read()
            self.assertEqual(estatico.status, 200)
            conexion.close()
        finally:
            servidor.close()
            hilo.join(timeout=10)
        self.assertFalse(hilo.is_alive())
