"""Pruebas del consolidado (SDD RF-16, casos 1 y 11 de la sección 17.2).

Las pruebas de acceso por HTTP (403 para junior y senior, redirección sin sesión) se agregan junto con la vista,
cuando el equipo apruebe el wireframe de la pantalla.
"""
import datetime

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import override_settings

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
