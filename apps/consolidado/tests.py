"""Pruebas del consolidado (SDD RF-16, casos 1 y 11 de la sección 17.2): servicio de datos y pantalla."""
import datetime
import re

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import override_settings
from django.urls import reverse

from apps.consolidado.servicios import datos_consolidado
from apps.cuentas.models import Usuario
from apps.entregables.models import Entregable
from apps.entregables.test_filtros import FiltrosBase

E = Entregable.Estado


class AccesoTests(FiltrosBase):
    def test_solo_gerente_y_admin(self):
        for usuario in (self.gerente, self.admin):
            with self.subTest(usuario=usuario.username):
                self.assertEqual(datos_consolidado(usuario, hoy=self.hoy)["total"], 9)

    def test_junior_senior_y_anonimo_reciben_acceso_denegado(self):
        for usuario in (self.j1, self.j2, self.s1, self.s2, AnonymousUser()):
            with self.subTest(usuario=str(usuario)):
                with self.assertRaises(PermissionDenied):
                    datos_consolidado(usuario, hoy=self.hoy)


class CifrasTests(FiltrosBase):
    """Los números del consolidado deben coincidir con los datos."""

    def setUp(self):
        self.datos = datos_consolidado(self.gerente, hoy=self.hoy)

    def test_contadores_por_estado_coinciden_con_la_base_de_datos(self):
        contadores = {c["estado"]: c["total"] for c in self.datos["por_estado"]}
        self.assertEqual([c["estado"] for c in self.datos["por_estado"]], list(E.values))  # orden del tablero
        for estado in E.values:
            self.assertEqual(contadores[estado], Entregable.objects.filter(estado=estado).count(), estado)
        self.assertEqual(contadores, {"A_REALIZAR": 2, "EN_PROCESO": 4, "VERIFICACION_SENIOR": 1,
                                      "LISTO_PARA_ENTREGA": 1, "HECHO": 1})
        self.assertEqual(sum(contadores.values()), self.datos["total"])
        self.assertEqual(self.datos["activos"], Entregable.objects.exclude(estado=E.HECHO).count())

    def test_vencidos_y_proximos(self):
        self.assertEqual([e.titulo for e in self.datos["vencidos"]], ["a-vencido", "h-vencido"])
        self.assertEqual([e.titulo for e in self.datos["proximos"]], ["b-hoy", "c-critico", "d-proximo", "f-proximo"])
        self.assertEqual(self.datos["ventana_dias"], 7)

    def test_un_entregable_hecho_no_cuenta_como_vencido(self):
        self.assertNotIn("g-hecho", [e.titulo for e in self.datos["vencidos"]])

    def test_la_ventana_de_proximos_se_configura(self):
        self.assertEqual([e.titulo for e in datos_consolidado(self.gerente, hoy=self.hoy, ventana=2)["proximos"]],
                         ["b-hoy", "c-critico"])
        self.assertEqual([e.titulo for e in datos_consolidado(self.gerente, hoy=self.hoy, ventana=0)["proximos"]],
                         ["b-hoy"])
        with override_settings(CONSOLIDADO_WINDOW_DAYS=3):
            self.assertEqual(len(datos_consolidado(self.gerente, hoy=self.hoy)["proximos"]), 2)

    def test_resumen_por_cliente(self):
        por_cliente = {c["nombre"]: c for c in self.datos["por_cliente"]}
        demo = por_cliente["Cliente Demo"]
        self.assertEqual((demo["total"], demo["activos"], demo["vencidos"]), (7, 6, 2))
        self.assertEqual(demo["por_estado"], {"A_REALIZAR": 2, "EN_PROCESO": 3, "VERIFICACION_SENIOR": 0,
                                              "LISTO_PARA_ENTREGA": 1, "HECHO": 1})
        segundo = por_cliente["Segundo Cliente"]
        self.assertEqual((segundo["total"], segundo["activos"], segundo["vencidos"]), (2, 2, 0))
        self.assertEqual(sum(c["total"] for c in self.datos["por_cliente"]), self.datos["total"])

    def test_resumen_por_contrato(self):
        por_contrato = {c["nombre"]: c for c in self.datos["por_contrato"]}
        self.assertEqual({k: (v["total"], v["activos"], v["vencidos"]) for k, v in por_contrato.items()},
                         {"C1": (4, 3, 1), "C2": (3, 3, 1), "C3": (2, 2, 0)})
        self.assertEqual(por_contrato["C3"]["cliente"], "Segundo Cliente")
        for c in self.datos["por_contrato"]:
            self.assertEqual(sum(c["por_estado"].values()), c["total"])

    def test_carga_por_persona_cuenta_solo_activos(self):
        juniors = {p["usuario"].username: p["activos"] for p in self.datos["carga_juniors"]}
        seniors = {p["usuario"].username: p["activos"] for p in self.datos["carga_seniors"]}
        self.assertEqual(juniors, {"j1": 4, "j2": 4})  # g-hecho de j1 no cuenta
        self.assertEqual(seniors, {"s1": 5, "s2": 3})
        self.assertEqual(sum(juniors.values()), self.datos["activos"])
        self.assertEqual(sum(seniors.values()), self.datos["activos"])

    def test_la_carga_incluye_a_quien_no_tiene_nada(self):
        Usuario.objects.create_user("j3", password="x", rol="JUNIOR")
        juniors = {p["usuario"].username: p["activos"] for p in datos_consolidado(self.gerente, hoy=self.hoy)["carga_juniors"]}
        self.assertEqual(juniors["j3"], 0)

    def test_la_carga_se_ordena_de_mayor_a_menor(self):
        activos = [p["activos"] for p in self.datos["carga_seniors"]]
        self.assertEqual(activos, sorted(activos, reverse=True))


class FiltrosDelConsolidadoTests(FiltrosBase):
    def consolidado(self, **params):
        return datos_consolidado(self.gerente, params, hoy=self.hoy)

    def test_filtro_por_cliente_afecta_a_toda_la_pantalla(self):
        d = self.consolidado(cliente=self.cliente2.pk)
        self.assertEqual((d["total"], d["activos"]), (2, 2))
        self.assertEqual([c["nombre"] for c in d["por_cliente"]], ["Segundo Cliente"])
        self.assertEqual({c["estado"]: c["total"] for c in d["por_estado"]}["EN_PROCESO"], 1)
        self.assertEqual([e.titulo for e in d["proximos"]], ["c-critico", "d-proximo"])
        self.assertEqual(sum(p["activos"] for p in d["carga_juniors"]), 2)

    def test_filtro_por_contrato(self):
        d = self.consolidado(contrato=self.c2.pk)
        self.assertEqual(d["total"], 3)
        self.assertEqual([e.titulo for e in d["vencidos"]], ["h-vencido"])

    def test_filtro_por_estado(self):
        d = self.consolidado(estado="EN_PROCESO")
        contadores = {c["estado"]: c["total"] for c in d["por_estado"]}
        self.assertEqual(contadores["EN_PROCESO"], 4)
        self.assertEqual(sum(v for k, v in contadores.items() if k != "EN_PROCESO"), 0)

    def test_filtro_por_rango_de_fechas_del_plazo(self):
        hoy = self.hoy
        d = self.consolidado(desde=hoy.isoformat(), hasta=(hoy + datetime.timedelta(days=4)).isoformat())
        self.assertEqual(d["total"], 3)  # b (hoy), c (+2) y d (+4)
        self.assertEqual(d["filtros"]["desde"], hoy)
        d = self.consolidado(hasta=(hoy - datetime.timedelta(days=1)).isoformat())
        self.assertEqual(d["total"], 3)  # a (-3), h (-1) y g (-20)

    def test_valores_no_validos_se_ignoran(self):
        d = self.consolidado(cliente="x", contrato="", estado="ZZZ", desde="ayer", hasta="2026-13-45")
        self.assertEqual(d["filtros"], {})
        self.assertEqual(d["total"], 9)

    def test_filtros_combinados(self):
        d = self.consolidado(cliente=self.cliente.pk, estado="EN_PROCESO")
        self.assertEqual(d["total"], 3)  # a, b y h
        self.assertEqual(sorted(e.titulo for e in d["vencidos"]), ["a-vencido", "h-vencido"])


class PantallaTests(FiltrosBase):
    """La pantalla /consolidado/: acceso por rol y que muestre las mismas cifras que el servicio."""

    def ver(self, usuario, params=None):
        self.client.force_login(usuario)
        return self.client.get(reverse("consolidado"), params or {})

    def test_la_ruta_es_la_del_sdd(self):
        self.assertEqual(reverse("consolidado"), "/consolidado/")

    def test_sin_sesion_va_al_ingreso(self):
        r = self.client.get(reverse("consolidado"))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith(reverse("login")))

    def test_junior_y_senior_reciben_403_y_gerente_y_admin_la_ven(self):
        esperado = {"j1": 403, "j2": 403, "s1": 403, "s2": 403, "ger": 200, "adm": 200}
        for nombre, codigo in esperado.items():
            with self.subTest(usuario=nombre):
                self.assertEqual(self.ver(getattr(self, {"ger": "gerente", "adm": "admin"}.get(nombre, nombre))).status_code, codigo)

    def test_es_de_solo_lectura(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.post(reverse("consolidado")).status_code, 200)  # un POST no cambia nada ni falla
        self.assertEqual(Entregable.objects.count(), 9)

    def test_los_contadores_por_estado_se_muestran_en_el_orden_del_tablero(self):
        html = self.ver(self.gerente).content.decode()
        contadores = re.findall(r'<div class="contador"><b>(\d+)</b>([^<]+)</div>', html)
        self.assertEqual(contadores, [("2", "A realizar"), ("4", "En proceso"), ("1", "Verificación senior"),
                                      ("1", "Listo para entrega"), ("1", "Hecho")])
        self.assertContains(self.ver(self.gerente), "9 entregables en total · 8 activos")

    def test_vencidos_y_proximos_enlazan_al_detalle(self):
        r = self.ver(self.gerente)
        self.assertContains(r, "Vencidos (2)")
        self.assertContains(r, "Próximos a vencer — en los próximos 7 días (4)")
        for e in (self.a, self.h, self.b, self.c):
            self.assertContains(r, reverse("entregable_detalle", args=[e.pk]))
        self.assertNotContains(r, reverse("entregable_detalle", args=[self.g.pk]))  # el hecho no es vencido ni próximo

    def test_resumenes_por_cliente_y_por_contrato(self):
        html = self.ver(self.gerente).content.decode()
        self.assertRegex(html, r"<tr><td>Cliente Demo</td><td class=\"num\">7</td><td class=\"num\">6</td><td class=\"num\">2</td>"
                               r"\s*<td class=\"num\">2</td><td class=\"num\">3</td><td class=\"num\">0</td><td class=\"num\">1</td><td class=\"num\">1</td></tr>")
        self.assertRegex(html, r"<tr><td>C3</td><td>Segundo Cliente</td><td class=\"num\">2</td>")
        # una columna por estado, con su etiqueta, en cada resumen
        self.assertEqual(html.count('<th class="num">Verificación senior</th>'), 2)

    def test_carga_por_persona_con_barras_proporcionales(self):
        html = self.ver(self.gerente).content.decode()
        self.assertRegex(html, r'<span class="nombre">s1</span>\s*<div class="barra-carga" aria-hidden="true"><i style="width:100%"></i></div><b>5</b>')
        self.assertRegex(html, r'<span class="nombre">s2</span>\s*<div class="barra-carga" aria-hidden="true"><i style="width:60%"></i></div><b>3</b>')

    def test_las_barras_no_dividen_por_cero(self):
        Entregable.objects.all().delete()
        r = self.ver(self.gerente)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'style="width:0%"')

    def test_los_filtros_se_aplican_y_el_panel_queda_abierto(self):
        r = self.ver(self.gerente, {"cliente": self.cliente2.pk})
        self.assertContains(r, "2 entregables en total")
        self.assertContains(r, '<details class="filtros" open>')
        self.assertContains(r, f'<option value="{self.cliente2.pk}" selected>Segundo Cliente</option>')
        self.assertContains(r, "1 activo<")
        self.assertEqual([f["nombre"] for f in r.context["por_cliente"]], ["Segundo Cliente"])

    def test_sin_filtros_el_panel_esta_cerrado_y_dice_cero_activos(self):
        r = self.ver(self.gerente)
        self.assertContains(r, '<details class="filtros">')
        self.assertContains(r, "0 activos")

    def test_los_valores_invalidos_se_ignoran_sin_error(self):
        r = self.ver(self.gerente, {"cliente": "x", "estado": "ZZZ", "desde": "ayer"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "9 entregables en total")

    def test_un_filtro_sin_resultados_lo_dice_en_cada_tabla(self):
        r = self.ver(self.gerente, {"desde": "2020-01-01", "hasta": "2020-01-02"})
        self.assertContains(r, "No hay entregables vencidos.")
        self.assertContains(r, "No hay entregables por vencer en ese período.")
        self.assertContains(r, "Sin datos con esos filtros.", count=2)

    def test_los_selectores_tienen_etiqueta(self):
        html = self.ver(self.gerente).content.decode()
        for campo, etiqueta in (("f-cliente", "Cliente"), ("f-contrato", "Contrato"), ("f-estado", "Estado"),
                                ("f-desde", "Plazo desde"), ("f-hasta", "Plazo hasta")):
            self.assertIn(f'<label for="{campo}">{etiqueta}</label>', html)

    def test_aclara_que_la_exportacion_llega_despues(self):
        self.assertContains(self.ver(self.gerente), "La exportación y los reportes avanzados llegan en la fase 3")

    def test_no_se_cachea(self):
        self.assertIn("no-store", self.ver(self.gerente)["Cache-Control"])
