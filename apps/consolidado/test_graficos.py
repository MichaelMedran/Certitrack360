"""Pruebas de los gráficos gerenciales (SDD del Sprint 3, RF-49, HU-22; caso 39 de la sección 13)."""
import datetime
import re

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.consolidado import graficos
from apps.consolidado.servicios import datos_consolidado, datos_graficos
from apps.entregables.models import Entregable
from apps.entregables.test_filtros import FiltrosBase
from apps.entregables.testing import entregar

E = Entregable.Estado


class DatosDeEntregas(FiltrosBase):
    """Suma dos entregas conocidas al conjunto de FiltrosBase: una a tiempo (marzo) y una tarde (abril)."""

    def setUp(self):
        a = self.nuevo(self.c1, self.j1, self.s1, "z-a-tiempo", E.LISTO_PARA_ENTREGA, 0)
        b = self.nuevo(self.c3, self.j2, self.s1, "z-tarde", E.LISTO_PARA_ENTREGA, 0)
        Entregable.objects.filter(pk=a.pk).update(plazo=datetime.date(2026, 3, 20), fecha_recepcion=datetime.date(2026, 3, 10))
        Entregable.objects.filter(pk=b.pk).update(plazo=datetime.date(2026, 4, 1), fecha_recepcion=datetime.date(2026, 4, 1))
        a.refresh_from_db()
        b.refresh_from_db()
        entregar(a, self.s1, fecha_entrega=datetime.date(2026, 3, 18))  # 8 días, a tiempo
        entregar(b, self.s1, fecha_entrega=datetime.date(2026, 4, 5))  # 4 días, tarde


class AccesoGraficosTests(FiltrosBase):
    def test_solo_gerente_y_admin_reciben_los_datos(self):
        for usuario in (self.gerente, self.admin):
            with self.subTest(usuario=usuario.username):
                self.assertIn("activos_por_persona", datos_graficos(usuario))

    def test_junior_senior_y_anonimo_reciben_acceso_denegado(self):
        for usuario in (self.j1, self.j2, self.s1, self.s2, AnonymousUser()):
            with self.subTest(usuario=str(usuario)):
                with self.assertRaises(PermissionDenied):
                    datos_graficos(usuario)

    def test_la_pantalla_da_403_a_junior_y_senior_y_200_a_gerente_y_admin(self):
        for usuario, codigo in ((self.j1, 403), (self.s1, 403), (self.gerente, 200), (self.admin, 200)):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                self.assertEqual(self.client.get(reverse("consolidado")).status_code, codigo)

    def test_sin_sesion_va_al_ingreso(self):
        self.assertEqual(self.client.get(reverse("consolidado")).status_code, 302)


class CifrasGraficosTests(DatosDeEntregas):
    def setUp(self):
        super().setUp()
        self.datos = datos_graficos(self.gerente)

    def test_son_exactamente_cuatro_graficos(self):
        self.client.force_login(self.gerente)
        r = self.client.get(reverse("consolidado"))
        self.assertEqual([g["id"] for g in r.context["graficos"]], ["g-personas", "g-cumplidos", "g-atencion", "g-errores"])
        self.assertContains(r, "<svg", count=4)

    def test_activos_por_persona(self):
        filas = {(p["nombre"], p["rol"]): p["activos"] for p in self.datos["activos_por_persona"]}
        activos_j1 = Entregable.objects.filter(junior_asignado=self.j1).exclude(estado=E.HECHO).count()
        self.assertEqual(filas[(self.j1.nombre, "Junior")], activos_j1)
        self.assertEqual(filas[(self.s1.nombre, "Senior")], Entregable.objects.filter(senior_revisor=self.s1).exclude(estado=E.HECHO).count())
        self.assertEqual(sum(p["activos"] for p in self.datos["activos_por_persona"] if p["rol"] == "Junior"),
                         Entregable.objects.exclude(estado=E.HECHO).count())

    def test_porcentaje_dentro_del_plazo_por_mes(self):
        por_mes = {m["mes"]: m for m in self.datos["cumplidos_por_mes"]}
        self.assertEqual(por_mes["03/2026"], {"mes": "03/2026", "entregados": 1, "a_tiempo": 1, "porcentaje": 100})
        self.assertEqual(por_mes["04/2026"], {"mes": "04/2026", "entregados": 1, "a_tiempo": 0, "porcentaje": 0})
        self.assertEqual([m["mes"] for m in self.datos["cumplidos_por_mes"]][:2], ["03/2026", "04/2026"])  # cronológico

    def test_tiempo_promedio_de_atencion_por_cliente(self):
        por_cliente = {c["cliente"]: c for c in self.datos["atencion_por_cliente"]}
        self.assertEqual(por_cliente["Cliente Demo"]["dias_promedio"], 4.0)  # (8 + 0) / 2: g-hecho no tiene fecha previa
        self.assertEqual((por_cliente["Segundo Cliente"]["entregados"], por_cliente["Segundo Cliente"]["dias_promedio"]), (1, 4.0))

    def test_observaciones_por_tipo_de_error(self):
        tipos = {o["tipo_error"]: o["cantidad"] for o in self.datos["observaciones_por_tipo"]}
        self.assertEqual(tipos, {"FORMATO": 5, "CONTENIDO": 2})
        self.assertEqual(self.datos["observaciones_por_tipo"][0]["tipo_error"], "FORMATO")  # el mayor primero

    def test_se_actualizan_con_lo_registrado_sin_cargas_manuales(self):
        from apps.entregables.models import Observacion

        Observacion.objects.create(entregable=self.a, autor=self.s1, tipo_error="PLAZO", descripcion="x")
        tipos = {o["tipo_error"]: o["cantidad"] for o in datos_graficos(self.gerente)["observaciones_por_tipo"]}
        self.assertEqual(tipos["PLAZO"], 1)


class FiltrosGraficosTests(DatosDeEntregas):
    def test_filtro_por_cliente(self):
        datos = datos_graficos(self.gerente, {"cliente": str(self.cliente2.pk)})
        self.assertEqual([c["cliente"] for c in datos["atencion_por_cliente"]], ["Segundo Cliente"])
        self.assertEqual({o["tipo_error"]: o["cantidad"] for o in datos["observaciones_por_tipo"]}, {"CONTENIDO": 2, "FORMATO": 1})
        self.assertEqual(datos["texto_filtro"], "Filtro aplicado: Cliente: Segundo Cliente")

    def test_filtro_por_sector_del_cliente(self):
        datos = datos_graficos(self.gerente, {"sector": "TELECOM"})
        self.assertEqual({p["nombre"]: p["activos"] for p in datos["activos_por_persona"] if p["rol"] == "Junior"},
                         {self.j1.nombre: 1, self.j2.nombre: 1})
        self.assertEqual([c["cliente"] for c in datos["atencion_por_cliente"]], ["Segundo Cliente"])
        self.assertEqual(datos["texto_filtro"], "Filtro aplicado: Sector: Telecomunicaciones")
        self.assertEqual(datos_graficos(self.gerente, {"sector": "NO_EXISTE"})["texto_filtro"], "Sin filtros")

    def test_filtro_por_contrato(self):
        datos = datos_graficos(self.gerente, {"contrato": str(self.c3.pk)})
        self.assertEqual(sum(p["activos"] for p in datos["activos_por_persona"] if p["rol"] == "Senior"), 2)
        self.assertEqual(datos["texto_filtro"], "Filtro aplicado: Contrato: C3")

    def test_filtro_por_rango_de_fechas_del_plazo(self):
        datos = datos_graficos(self.gerente, {"desde": "2026-04-01", "hasta": "2026-04-30"})
        self.assertEqual([m["mes"] for m in datos["cumplidos_por_mes"]], ["04/2026"])
        self.assertEqual(datos["observaciones_por_tipo"], [])
        self.assertEqual(datos["texto_filtro"], "Filtro aplicado: Plazo desde 01/04/2026 · Plazo hasta 30/04/2026")

    def test_filtros_invalidos_se_ignoran(self):
        datos = datos_graficos(self.gerente, {"cliente": "abc", "desde": "mal", "sector": "x", "contrato": "99999999999999999999999"})
        self.assertEqual(datos["texto_filtro"], "Sin filtros")

    def test_el_filtro_nunca_amplia_la_visibilidad(self):
        # Un gerente ve todo, así que se comprueba con el servicio que parte de entregables_visibles: un id inexistente no devuelve nada.
        self.assertEqual(datos_graficos(self.gerente, {"cliente": "999999"})["activos_por_persona"], [])

    def test_el_consolidado_acepta_el_sector_sin_cambiar_sus_cifras(self):
        sin = datos_consolidado(self.gerente, hoy=self.hoy)
        con = datos_consolidado(self.gerente, {"sector": "TELECOM"}, hoy=self.hoy)
        self.assertEqual(con["total"], 3)  # c-critico, d-proximo y la entrega «z-tarde» del contrato C3
        self.assertEqual(con["filtros"], {"sector": "TELECOM"})
        self.assertGreater(sin["total"], con["total"])

    def test_la_pantalla_muestra_el_filtro_aplicado_en_cada_grafico(self):
        self.client.force_login(self.gerente)
        r = self.client.get(reverse("consolidado"), {"cliente": self.cliente2.pk, "sector": "TELECOM"})
        self.assertContains(r, "<strong>Filtro aplicado: Cliente: Segundo Cliente · Sector: Telecomunicaciones</strong>", count=4)
        r = self.client.get(reverse("consolidado"))
        self.assertContains(r, "<strong>Sin filtros</strong>", count=4)


class PantallaGraficosTests(DatosDeEntregas):
    def ver(self, **params):
        self.client.force_login(self.gerente)
        return self.client.get(reverse("consolidado"), params)

    def test_cada_grafico_trae_titulo_descripcion_y_tabla_de_datos(self):
        html = self.ver().content.decode()
        self.assertEqual(html.count('role="img"'), 4)
        self.assertEqual(html.count("<details class=\"datos-grafico\""), 4)
        self.assertIn('aria-label="Observaciones por tipo de error"', html)
        self.assertRegex(html, r"<title>[^<]*: 5</title>")  # el valor de cada barra, en texto

    def test_sin_datos_lo_dice_en_texto(self):
        r = self.ver(cliente=999999)
        self.assertContains(r, "No hay datos de entregables activos con este filtro.")
        self.assertContains(r, "No hay datos de entregas con este filtro.", count=2)
        self.assertContains(r, "No hay observaciones registradas con este filtro.")
        self.assertNotContains(r, "<svg")

    def test_no_agrega_javascript_ni_direcciones_externas(self):
        html = self.ver().content.decode()
        bloque = html[html.index('<h2 id="graficos">'):]
        self.assertNotIn("<script", bloque)
        self.assertIsNone(re.search(r"\son[a-z]+=", bloque))
        sin_xmlns = bloque.replace("http://www.w3.org/2000/svg", "")
        self.assertNotRegex(sin_xmlns, r"https?://")

    def test_el_campo_sector_esta_en_el_formulario(self):
        self.assertContains(self.ver(), 'name="sector"')


class FuncionesSvgTests(FiltrosBase):
    def test_sin_filas_no_hay_svg(self):
        self.assertEqual(graficos.barras_horizontales("t", []), "")
        self.assertEqual(graficos.barras_verticales("t", []), "")

    def test_el_texto_se_escapa(self):
        svg = graficos.barras_horizontales("Título <b>", [('Ana <script>alert(1)</script>', 3, "3")])
        self.assertNotIn("<script", svg)
        self.assertIn("&lt;script&gt;", svg)
        self.assertIn("&lt;b&gt;", svg)

    def test_las_barras_son_proporcionales(self):
        svg = graficos.barras_horizontales("t", [("a", 10, "10"), ("b", 5, "5")])
        anchos = [float(x) for x in re.findall(r'width="([\d.]+)" height="20" rx="3" fill="#1e4e8c"', svg)]
        self.assertAlmostEqual(anchos[0], 2 * anchos[1], places=0)

    def test_cero_no_dibuja_barra_pero_si_el_valor_escrito(self):
        svg = graficos.barras_horizontales("t", [("a", 0, "0"), ("b", 2, "2")])
        self.assertEqual(svg.count('fill="#1e4e8c"/>'), 1)
        self.assertIn(">0</text>", svg)

    def test_las_etiquetas_largas_se_acortan_pero_van_completas_en_el_titulo(self):
        largo = "Cliente con un nombre extraordinariamente largo S.A.C."
        svg = graficos.barras_horizontales("t", [(largo, 1, "1")])
        self.assertIn(f"<title>{largo}: 1</title>", svg)
        self.assertIn("…</text>", svg)

    def test_barras_verticales_con_maximo_cien(self):
        svg = graficos.barras_verticales("t", [("03/2026", 100, "100 %"), ("04/2026", 50, "50 %")])
        self.assertIn("100 %", svg)
        self.assertIn('role="img"', svg)
