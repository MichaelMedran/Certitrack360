"""Pruebas de la interfaz común: Inicio, notificaciones, barra de navegación, caché y recursos locales (SDD §12, §13)."""
import re
from types import SimpleNamespace

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve, reverse

from apps.alertas.models import Notificacion
from apps.cuentas.context_processors import SECCIONES, navegacion
from apps.cuentas.middleware import SinCacheEnPaginasPrivadas
from apps.cuentas.models import Usuario
from apps.entregables.models import Entregable
from apps.entregables.tests import Base

E = Entregable.Estado


class InicioTests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.vencido = cls.nuevo(cls.c1, cls.j1, cls.s1, "vencido", E.EN_PROCESO, -2)
        cls.pronto = cls.nuevo(cls.c1, cls.j1, cls.s1, "pronto", E.EN_PROCESO, 3)
        cls.en_ver = cls.nuevo(cls.c1, cls.j1, cls.s1, "en-ver", E.VERIFICACION_SENIOR, 8)
        cls.hecho = cls.nuevo(cls.c1, cls.j1, cls.s1, "hecho", E.HECHO, -5)

    def ver(self, usuario):
        self.client.force_login(usuario)
        return self.client.get(reverse("inicio"))

    def cifras(self, usuario):
        c = self.ver(usuario).context
        return c["total_activos"], c["vencidos"], c["por_vencer"], c["en_verificacion"]

    def test_las_cifras_cuentan_solo_lo_que_cada_rol_puede_ver(self):
        self.assertEqual(self.cifras(self.j1), (4, 1, 1, 1))       # E1, vencido, pronto y en-ver; «hecho» no cuenta
        self.assertEqual(self.cifras(self.s1), (4, 1, 1, 1))
        self.assertEqual(self.cifras(self.j2), (1, 0, 0, 0))       # solo E2
        self.assertEqual(self.cifras(self.gerente), (5, 1, 1, 1))  # todo
        self.assertEqual(self.cifras(self.admin), (5, 1, 1, 1))

    def test_un_entregable_hecho_no_cuenta_como_vencido_ni_activo(self):
        self.assertEqual(self.ver(self.j1).context["vencidos"], 1)
        self.assertNotIn("hecho", [e.titulo for e in self.ver(self.j1).context["proximos"]])

    def test_las_cuatro_cifras_van_con_su_rotulo(self):
        html = self.ver(self.j1).content.decode()
        self.assertRegex(html, r'<div class="cifra">4</div>Entregables activos')
        self.assertRegex(html, r'<div class="cifra rojo">1</div>Vencidos')
        self.assertRegex(html, r'<div class="cifra ambar">1</div>Vencen en 5 días')
        self.assertRegex(html, r'<div class="cifra">1</div>En verificación senior')

    @override_settings(ALERT_THRESHOLDS_DAYS=[10, 4, 0])
    def test_la_ventana_de_por_vencer_es_la_de_las_alertas(self):
        r = self.ver(self.j1)
        self.assertContains(r, "Vencen en 10 días")
        self.assertEqual(r.context["por_vencer"], 3)  # pronto (+3), en-ver (+8) y E1 (+10)

    def test_proximos_plazos_ordenados_por_fecha_y_solo_activos(self):
        r = self.ver(self.j1)
        self.assertEqual([e.titulo for e in r.context["proximos"]], ["vencido", "pronto", "en-ver", "E1"])
        for e in r.context["proximos"]:
            self.assertContains(r, reverse("entregable_detalle", args=[e.pk]))

    def test_los_proximos_plazos_se_limitan_a_seis(self):
        for i in range(8):
            self.nuevo(self.c1, self.j1, self.s1, f"extra{i}", dias=20 + i)
        self.assertEqual(len(self.ver(self.j1).context["proximos"]), 6)

    def test_saluda_por_el_nombre_o_por_el_usuario(self):
        self.assertContains(self.ver(self.j1), "Hola, j1")
        Usuario.objects.filter(pk=self.j1.pk).update(first_name="Javier")
        self.assertContains(self.ver(Usuario.objects.get(pk=self.j1.pk)), "Hola, Javier")

    def test_el_texto_de_apoyo_depende_del_rol(self):
        esperado = {self.j1: "Resumen de las tareas que tiene asignadas.", self.s1: "Resumen de los proyectos a su cargo.",
                    self.gerente: "Resumen general de todos los proyectos.", self.admin: "Resumen general de todos los proyectos."}
        for usuario, texto in esperado.items():
            with self.subTest(usuario=usuario.username):
                self.assertContains(self.ver(usuario), texto)

    def test_el_acceso_al_consolidado_es_solo_para_gerente_y_admin(self):
        for usuario, ve in ((self.gerente, True), (self.admin, True), (self.s1, False), (self.j1, False)):
            with self.subTest(usuario=usuario.username):
                self.assertEqual("Ver consolidado" in self.ver(usuario).content.decode(), ve)

    def test_sin_nada_pendiente_lo_dice(self):
        sin_nada = Usuario.objects.create_user("j_nuevo", password="x", rol="JUNIOR")
        r = self.ver(sin_nada)
        self.assertContains(r, "No tiene entregables pendientes.")
        self.assertContains(r, "No tiene notificaciones.")
        self.assertEqual(self.cifras(sin_nada), (0, 0, 0, 0))

    def test_notificaciones_recientes_son_las_cinco_ultimas_y_solo_las_propias(self):
        for i in range(7):
            Notificacion.objects.create(usuario=self.j1, entregable=self.e1, tipo="ASIGNACION", mensaje=f"aviso {i}")
        Notificacion.objects.create(usuario=self.j2, entregable=self.e2, tipo="ASIGNACION", mensaje="aviso ajeno")
        r = self.ver(self.j1)
        self.assertEqual([n.mensaje for n in r.context["recientes"]], [f"aviso {i}" for i in (6, 5, 4, 3, 2)])
        self.assertNotContains(r, "aviso ajeno")
        self.assertContains(r, reverse("notificaciones"))  # «Ver todas»
        self.assertContains(r, f'href="{reverse("entregable_detalle", args=[self.e1.pk])}">Ver</a>')

    def test_se_distinguen_las_leidas_de_las_no_leidas_con_texto(self):
        Notificacion.objects.create(usuario=self.j1, entregable=self.e1, tipo="ASIGNACION", mensaje="nueva")
        Notificacion.objects.create(usuario=self.j1, entregable=self.e1, tipo="ASIGNACION", mensaje="vista", leida=True)
        html = self.ver(self.j1).content.decode()
        self.assertEqual(html.count(">Sin leer</span>"), 1)
        self.assertRegex(html, r">Sin leer</span> nueva")

    def test_el_indicador_de_la_barra_cuenta_las_no_leidas(self):
        for i in range(3):
            Notificacion.objects.create(usuario=self.j1, entregable=self.e1, tipo="ASIGNACION", mensaje=f"n{i}")
        self.assertContains(self.ver(self.j1), '<span class="insignia" aria-label="3 sin leer">3</span>')
        self.assertNotContains(self.ver(self.j2), "insignia")


class NotificacionesPantallaTests(Base):
    def setUp(self):
        self.n1 = Notificacion.objects.create(usuario=self.j1, entregable=self.e1, tipo="ASIGNACION", mensaje="uno")
        self.n2 = Notificacion.objects.create(usuario=self.j1, entregable=self.e1, tipo="OBSERVACION", mensaje="dos")
        self.n3 = Notificacion.objects.create(usuario=self.j1, entregable=self.e1, tipo="VENCIMIENTO", umbral=2,
                                              mensaje="tres", leida=True)
        Notificacion.objects.create(usuario=self.j2, entregable=self.e2, tipo="ASIGNACION", mensaje="de otra persona")

    def ver(self, usuario=None):
        self.client.force_login(usuario or self.j1)
        return self.client.get(reverse("notificaciones"))

    def test_hay_un_boton_por_cada_aviso_sin_leer_y_ninguno_en_los_leidos(self):
        r = self.ver()
        self.assertContains(r, "Marcar como leída", count=2)
        for n, hay in ((self.n1, True), (self.n2, True), (self.n3, False)):
            self.assertEqual(f'action="{reverse("notificacion_leer", args=[n.pk])}"' in r.content.decode(), hay, n.mensaje)

    def test_cada_aviso_dice_su_estado_y_su_tipo_con_texto(self):
        html = self.ver().content.decode()
        self.assertEqual((html.count(">Sin leer</span>"), html.count(">Leída</span>")), (2, 1))
        for tipo in ("Asignación", "Observación", "Vencimiento"):
            self.assertIn(f'<span class="etiqueta">{tipo}</span>', html)

    def test_marcar_todas_aparece_solo_si_hay_sin_leer(self):
        self.assertContains(self.ver(), "Marcar todas como leídas")
        Notificacion.objects.filter(usuario=self.j1).update(leida=True)
        r = self.ver()
        self.assertNotContains(r, "Marcar todas como leídas")
        self.assertNotContains(r, "Marcar como leída")

    def test_solo_se_ven_las_propias_y_cada_una_enlaza_a_su_entregable(self):
        r = self.ver()
        self.assertNotContains(r, "de otra persona")
        self.assertContains(r, f'href="{reverse("entregable_detalle", args=[self.e1.pk])}">Ver</a>', count=3)

    def test_aclara_que_no_hay_mensajes_entre_personas(self):
        self.assertContains(self.ver(), "No hay mensajes entre personas.")

    def test_sin_avisos_lo_dice(self):
        self.assertContains(self.ver(self.gerente), "No tiene notificaciones.")

    def test_muestra_a_lo_sumo_los_cien_mas_recientes(self):
        Notificacion.objects.bulk_create([
            Notificacion(usuario=self.s1, entregable=self.e1, tipo="ASIGNACION", mensaje=f"m{i}") for i in range(105)])
        self.assertEqual(len(self.ver(self.s1).context["notificaciones"]), 100)

    def test_el_flujo_de_leer_deja_la_barra_en_cero(self):
        self.client.force_login(self.j1)
        self.assertContains(self.client.get(reverse("notificaciones")), 'aria-label="2 sin leer"')
        r = self.client.post(reverse("notificaciones_leidas"), follow=True)
        self.assertNotContains(r, "insignia")


class CacheDePaginasPrivadasTests(SimpleTestCase):
    def pasar(self, autenticado, respuesta=None):
        peticion = RequestFactory().get("/x/")
        peticion.user = SimpleNamespace(is_authenticated=autenticado)
        return SinCacheEnPaginasPrivadas(lambda _: respuesta or HttpResponse("ok"))(peticion)

    def test_a_quien_inicio_sesion_no_se_le_guardan_las_paginas(self):
        cabecera = self.pasar(True)["Cache-Control"]
        for directiva in ("no-store", "no-cache", "private"):
            self.assertIn(directiva, cabecera)

    def test_sin_sesion_no_se_agrega_nada(self):
        self.assertNotIn("Cache-Control", self.pasar(False))

    def test_respeta_la_politica_que_ya_trae_la_respuesta(self):
        propia = HttpResponse("archivo")
        propia["Cache-Control"] = "private, max-age=60"
        self.assertEqual(self.pasar(True, propia)["Cache-Control"], "private, max-age=60")

    def test_esta_activo_despues_de_la_autenticacion(self):
        orden = settings.MIDDLEWARE
        self.assertIn("apps.cuentas.middleware.SinCacheEnPaginasPrivadas", orden)
        self.assertGreater(orden.index("apps.cuentas.middleware.SinCacheEnPaginasPrivadas"),
                           orden.index("django.contrib.auth.middleware.AuthenticationMiddleware"))


class CacheEnLasPantallasTests(Base):
    def test_todas_las_pantallas_privadas_salen_sin_cache(self):
        self.client.force_login(self.gerente)
        rutas = [reverse(n) for n in ("inicio", "tablero", "entregables", "entregable_nuevo", "calendario", "asistente",
                                      "notificaciones", "consolidado")]
        rutas += [reverse("entregable_detalle", args=[self.e1.pk]), reverse("adm_lista", args=["plantillas"]),
                  reverse("adm_nuevo", args=["plantillas"])]
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                r = self.client.get(ruta)
                self.assertEqual(r.status_code, 200)
                self.assertIn("no-store", r["Cache-Control"])

    def test_tambien_los_fragmentos_htmx_y_los_errores(self):
        self.client.force_login(self.j1)
        self.assertIn("no-store", self.client.get(reverse("tablero"), HTTP_HX_REQUEST="true")["Cache-Control"])
        r = self.client.get(reverse("consolidado"))
        self.assertEqual(r.status_code, 403)
        self.assertIn("no-store", r["Cache-Control"])


class BarraDeNavegacionTests(SimpleTestCase):
    def seccion(self, ruta):
        peticion = RequestFactory().get(ruta)
        peticion.resolver_match = resolve(ruta)
        return navegacion(peticion)["seccion"]

    def test_cada_pantalla_activa_su_seccion(self):
        casos = {
            reverse("inicio"): "inicio", reverse("tablero"): "tablero", reverse("calendario"): "calendario",
            reverse("entregables"): "entregables", reverse("entregable_nuevo"): "entregables",
            reverse("entregable_detalle", args=[1]): "entregables", reverse("asistente"): "asistente",
            reverse("consolidado"): "consolidado", reverse("gestion"): "gestion",
            reverse("adm_lista", args=["plantillas"]): "gestion", reverse("adm_nuevo", args=["clientes"]): "gestion",
            reverse("adm_editar", args=["contratos", 3]): "gestion", reverse("notificaciones"): "avisos",
        }
        for ruta, seccion in casos.items():
            with self.subTest(ruta=ruta):
                self.assertEqual(self.seccion(ruta), seccion)

    def test_toda_seccion_nombrada_existe_en_las_urls(self):
        for nombre in SECCIONES:
            with self.subTest(nombre=nombre):
                self.assertTrue(any(
                    self._resuelve(nombre, args) for args in ([], [1], ["clientes"], ["clientes", 1])))

    @staticmethod
    def _resuelve(nombre, args):
        try:
            reverse(nombre, args=args)
            return True
        except Exception:  # noqa: BLE001 - NoReverseMatch con otros argumentos
            return False

    def test_las_pantallas_que_no_son_de_la_barra_no_marcan_nada(self):
        self.assertIsNone(self.seccion(reverse("login")))

    def test_sin_resolucion_de_ruta_no_marca_nada(self):
        self.assertIsNone(navegacion(RequestFactory().get("/"))["seccion"])


class PlantillaBaseTests(Base):
    PAGINAS = ("inicio", "tablero", "entregables", "entregable_nuevo", "calendario", "asistente", "notificaciones",
               "consolidado", "gestion")

    def paginas(self):
        self.client.force_login(self.gerente)
        for nombre in self.PAGINAS:
            yield nombre, self.client.get(reverse(nombre), follow=True).content.decode()
        yield "detalle", self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).content.decode()
        for entidad in ("clientes", "contratos", "plantillas"):
            yield f"nuevo {entidad}", self.client.get(reverse("adm_nuevo", args=[entidad])).content.decode()

    def test_es_un_documento_en_espanol_con_salto_al_contenido(self):
        for nombre, html in self.paginas():
            with self.subTest(pantalla=nombre):
                self.assertIn('<html lang="es">', html)
                self.assertIn('<a class="saltar" href="#contenido">Saltar al contenido</a>', html)
                self.assertIn('<main class="contenedor" id="contenido">', html)
                self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">', html)
                self.assertEqual(html.count("<h1"), 1)

    def test_ninguna_pantalla_pide_recursos_externos(self):
        externos = re.compile(r'(?:src|href|action|data-[a-z-]+)=["\']\s*(?:https?:)?//', re.I)
        paginas = dict(self.paginas())
        self.client.logout()
        paginas["login"] = self.client.get(reverse("login")).content.decode()
        for nombre, html in paginas.items():
            with self.subTest(pantalla=nombre):
                self.assertIsNone(externos.search(html))
                self.assertNotIn("@import", html)

    def test_los_archivos_estaticos_que_se_cargan_existen(self):
        for ruta in ("css/certitrack.css", "js/htmx.min.js", "js/certitrack.js", "js/tablero.js", "js/plantilla.js",
                     "js/Sortable.min.js"):
            with self.subTest(ruta=ruta):
                self.assertIsNotNone(finders.find(ruta), ruta)

    def test_los_scripts_comunes_se_cargan_diferidos(self):
        html = self.client.get(reverse("login")).content.decode()
        self.assertEqual(len(re.findall(r"<script src=\"[^\"]+\" defer></script>", html)), 2)
        self.assertNotRegex(html, r"<script>[^<]")  # sin scripts en línea

    def test_el_token_csrf_viaja_en_el_cuerpo_solo_con_sesion(self):
        self.client.force_login(self.j1)
        self.assertRegex(self.client.get(reverse("inicio")).content.decode(), r"<body hx-headers='\{\"X-CSRFToken\": \"[A-Za-z0-9]{32,}\"\}'>")
        self.client.logout()
        self.assertIn("<body>", self.client.get(reverse("login")).content.decode())

    def test_los_mensajes_se_anuncian_segun_su_gravedad(self):
        self.client.force_login(self.j1)
        url = reverse("entregable_estado", args=[self.e1.pk])
        mal = self.client.post(url, {"estado": "HECHO"}, follow=True).content.decode()
        self.assertRegex(mal, r'<div class="aviso aviso-error" role="alert">')
        bien = self.client.post(url, {"estado": "EN_PROCESO"}, follow=True).content.decode()
        self.assertRegex(bien, r'<div class="aviso aviso-success" role="status">')

    def test_las_pantallas_privadas_no_muestran_la_barra_sin_sesion(self):
        html = self.client.get(reverse("login")).content.decode()
        self.assertNotIn('class="barra"', html)
        self.assertNotIn("Consolidado", html)

    def test_la_barra_marca_la_pantalla_actual_con_aria_current(self):
        self.client.force_login(self.j1)
        html = self.client.get(reverse("tablero")).content.decode()
        self.assertEqual(re.findall(r'<a [^>]*aria-current="page"[^>]*>([^<]*)</a>', html), ["Tablero"])
