"""SDD del Sprint 2, hito S2-H1 · RF-21 (caso 14): cada evento del calendario identifica cliente, entregable (con su código)
y responsable, y la pantalla filtra por cliente, estado y responsable sin ampliar nunca lo que el usuario puede ver
(wireframe s2-calendario)."""
import datetime
import itertools

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.clientes.models import Cliente, Contrato
from apps.cuentas.models import Usuario
from apps.entregables.models import Entregable
from apps.entregables.test_filtros import FiltrosBase
from apps.entregables.visibilidad import entregables_visibles

E = Entregable.Estado
API = "/api/calendario/eventos/"


class CalendarioBase(FiltrosBase):
    def eventos(self, usuario, **params):
        self.client.force_login(usuario)
        r = self.client.get(reverse("calendario_eventos"), params)
        self.assertEqual(r.status_code, 200)
        return r.json()

    def ids(self, usuario, **params):
        return {ev["id"] for ev in self.eventos(usuario, **params)}

    def titulos(self, usuario, **params):
        return {Entregable.objects.get(pk=ev["id"]).titulo for ev in self.eventos(usuario, **params)}


class EventoConResponsableTests(CalendarioBase):
    def test_cada_evento_dice_estado_codigo_cliente_responsable_entregable_y_urgencia(self):
        por_id = {ev["id"]: ev for ev in self.eventos(self.gerente)}
        self.a.refresh_from_db()
        self.assertEqual(por_id[self.a.pk]["title"],
                         f"[{E.EN_PROCESO.label}] {self.a.codigo} Cliente Demo (a cargo de j1): a-vencido — Vencido")
        self.e2.refresh_from_db()
        self.assertEqual(por_id[self.e2.pk]["title"], f"[{E.A_REALIZAR.label}] {self.e2.codigo} Cliente Demo (a cargo de j2): E2")

    def test_el_responsable_es_el_junior_asignado_con_su_nombre(self):
        Usuario.objects.filter(pk=self.j1.pk).update(first_name="Julia", last_name="Jiménez")
        titulo = next(ev["title"] for ev in self.eventos(self.gerente) if ev["id"] == self.c.pk)
        self.assertIn("(a cargo de Julia Jiménez): c-critico — Crítico", titulo)
        self.assertIn("Segundo Cliente", titulo)

    def test_todos_los_eventos_llevan_su_codigo(self):
        for ev in self.eventos(self.gerente):
            self.assertIn(Entregable.objects.get(pk=ev["id"]).codigo, ev["title"])

    def test_los_datos_extra_del_evento_no_cambian(self):
        for ev in self.eventos(self.gerente):
            self.assertEqual(set(ev), {"id", "title", "start", "allDay", "url", "color", "extendedProps"})
            self.assertEqual(set(ev["extendedProps"]), {"estado", "urgencia"})


class FiltrosDeEventosTests(CalendarioBase):
    def test_por_cliente(self):
        self.assertEqual(self.titulos(self.gerente, cliente=self.cliente2.pk), {"c-critico", "d-proximo"})

    def test_por_estado(self):
        self.assertEqual(self.titulos(self.gerente, estado="EN_PROCESO"), {"a-vencido", "b-hoy", "c-critico", "h-vencido"})
        self.assertEqual(self.titulos(self.gerente, estado="HECHO"), {"g-hecho"})

    def test_por_responsable(self):
        self.assertEqual(self.titulos(self.gerente, responsable=self.j2.pk), {"E2", "d-proximo", "f-proximo", "h-vencido"})
        self.assertEqual(self.titulos(self.gerente, responsable=self.s2.pk), {"E2", "f-proximo", "h-vencido"})

    def test_combinados_y_con_el_rango_de_fechas(self):
        self.assertEqual(self.titulos(self.gerente, cliente=self.cliente.pk, estado="EN_PROCESO"),
                         {"a-vencido", "b-hoy", "h-vencido"})
        hoy = self.hoy.isoformat()
        self.assertEqual(self.titulos(self.gerente, estado="EN_PROCESO", start=hoy, end=hoy), {"b-hoy"})

    def test_los_valores_no_validos_se_ignoran(self):
        self.assertEqual(len(self.eventos(self.gerente, cliente="x", estado="NOPE", responsable="1; DROP")), 9)

    def test_un_junior_con_cliente_o_responsable_ajeno_no_obtiene_nada_ajeno(self):
        self.assertEqual(self.ids(self.j1, responsable=self.j2.pk), set())
        self.assertEqual(self.ids(self.j1, responsable=self.s2.pk), set())
        self.assertEqual(self.ids(self.s2, cliente=self.cliente2.pk), set())  # el contrato C3 es de s1
        otro = Cliente.objects.create(nombre="Tercer Cliente Ficticio", sector="PUBLICO")
        c4 = Contrato.objects.create(cliente=otro, numero_contrato="C4", fecha_inicio=datetime.date(2026, 1, 1),
                                     fecha_fin=datetime.date(2027, 1, 1), senior_responsable=self.s2)
        ajeno = self.nuevo(c4, self.j2, self.s2, "solo-de-j2")
        self.assertEqual(self.ids(self.j1, cliente=otro.pk), set())
        self.assertNotIn(ajeno.pk, self.ids(self.j1, cliente=otro.pk, responsable=self.j2.pk))

    def test_ninguna_combinacion_devuelve_algo_fuera_de_lo_visible(self):
        valores = {
            "cliente": [None, self.cliente.pk, self.cliente2.pk, 99999],
            "estado": [None, "EN_PROCESO", "HECHO"],
            "responsable": [None, self.j1.pk, self.j2.pk, self.s2.pk],
        }
        for usuario in (self.j1, self.j2, self.s1, self.s2, self.gerente, self.admin):
            visibles = set(entregables_visibles(usuario).values_list("pk", flat=True))
            for combinacion in itertools.product(*valores.values()):
                params = {k: v for k, v in zip(valores, combinacion) if v is not None}
                with self.subTest(usuario=usuario.username, **params):
                    self.assertLessEqual(self.ids(usuario, **params), visibles)


class DatosLimiteTests(CalendarioBase):
    """Revisión de S2-H1 (S2-H1-H2-ajustes): un valor extremo o mal escrito en la dirección nunca da un error 500."""

    ENORMES = ("99999999999999999999999", str(2**63), "-99999999999999999999999", "9" * 5000)

    def test_ids_fuera_de_rango_se_ignoran_en_la_api_y_en_la_pantalla(self):
        todos = self.ids(self.gerente)
        for valor in self.ENORMES:
            for clave in ("cliente", "responsable"):
                with self.subTest(clave=clave, valor=valor[:30]):
                    self.assertEqual(self.ids(self.gerente, **{clave: valor}), todos)
                    self.assertEqual(self.client.get(reverse("calendario"), {clave: valor}).status_code, 200)

    def test_un_id_inexistente_no_devuelve_nada(self):
        self.assertEqual(self.ids(self.gerente, cliente=2**63 - 1, responsable=2**63 - 1), set())

    def test_un_rango_de_fechas_mal_escrito_se_ignora(self):
        todos = self.ids(self.gerente)
        for start, end in (("abc", "xyz"), ("2026-13-45", "2026-02-30"), ("", ""), ("2026-11-01T00:00:00-05:00", "zzz")):
            with self.subTest(start=start, end=end):
                obtenidos = self.ids(self.gerente, start=start, end=end)
                self.assertLessEqual(obtenidos, todos)
        self.assertEqual(self.ids(self.gerente, start="nope", end="nope"), todos)
        hoy = self.hoy.isoformat()
        self.assertEqual(self.titulos(self.gerente, estado="EN_PROCESO", start=f"{hoy}T00:00:00-05:00",
                                      end=f"{hoy}T00:00:00-05:00"), {"b-hoy"})

    def test_la_api_no_hace_una_consulta_por_evento(self):
        self.client.force_login(self.gerente)

        def medir():
            with CaptureQueriesContext(connection) as consultas:
                n = len(self.client.get(reverse("calendario_eventos")).json())
            return n, len(consultas)

        n_antes, consultas_antes = medir()
        for i in range(4):
            self.nuevo(self.c3, self.j2, self.s1, f"extra-{i}")
        n_despues, consultas_despues = medir()
        self.assertEqual(n_despues, n_antes + 4)
        self.assertEqual(consultas_despues, consultas_antes)


class PaginaConFiltrosTests(CalendarioBase):
    def ver(self, usuario, params=None):
        self.client.force_login(usuario)
        return self.client.get(reverse("calendario"), params or {})

    def test_sin_filtros_el_panel_esta_cerrado_y_la_api_va_sin_parametros(self):
        r = self.ver(self.gerente)
        self.assertContains(r, '<details class="filtros">')
        self.assertContains(r, '<span class="chip" id="resumen-filtros">0 activos</span>')
        self.assertContains(r, f'events: "{API}",')

    def test_los_tres_filtros_con_su_etiqueta_y_el_boton_limpiar(self):
        html = self.ver(self.gerente).content.decode()
        for campo, nombre, etiqueta in (("f-cliente", "cliente", "Cliente"), ("f-estado", "estado", "Estado"),
                                        ("f-responsable", "responsable", "Responsable")):
            self.assertRegex(html, rf'<label for="{campo}">{etiqueta}</label>\s*<select id="{campo}" name="{nombre}">')
        self.assertIn(f'<a class="boton sec" href="{reverse("calendario")}">Limpiar</a>', html)
        self.assertIn(f'data-eventos="{API}"', html)
        for etiqueta in E.labels:
            self.assertIn(f">{etiqueta}</option>", html)

    def test_marca_los_filtros_aplicados_y_los_pasa_a_la_api(self):
        r = self.ver(self.gerente, {"cliente": self.cliente2.pk, "estado": "EN_PROCESO", "orden": "urgencia"})
        self.assertContains(r, '<details class="filtros" open>')
        self.assertContains(r, "2 activos")
        self.assertContains(r, f'<option value="{self.cliente2.pk}" selected>Segundo Cliente</option>')
        self.assertContains(r, '<option value="EN_PROCESO" selected>')
        self.assertEqual(r.context["consulta"], f"?cliente={self.cliente2.pk}&estado=EN_PROCESO")  # solo los del calendario
        self.assertContains(r, f'events: "{API}?cliente\\u003D{self.cliente2.pk}\\u0026estado\\u003DEN_PROCESO"')

    def test_las_opciones_solo_traen_lo_que_el_usuario_ve(self):
        r = self.ver(self.j2)
        opciones = r.context["opciones"]
        self.assertEqual({c.nombre for c in opciones["clientes"]}, {"Cliente Demo", "Segundo Cliente"})
        self.assertNotIn(self.j1, opciones["responsables"])
        self.assertNotContains(r, ">j1 (")

    def test_un_valor_ajeno_no_revela_nada(self):
        otro = Cliente.objects.create(nombre="Tercer Cliente Ficticio", sector="PUBLICO")
        r = self.ver(self.j1, {"cliente": otro.pk})
        self.assertNotContains(r, "Tercer Cliente Ficticio")
        self.assertEqual(self.ids(self.j1, cliente=otro.pk), set())

    def test_los_cuatro_roles_ven_la_pantalla(self):
        for usuario in (self.j1, self.s1, self.gerente, self.admin):
            with self.subTest(usuario=usuario.username):
                self.assertEqual(self.ver(usuario, {"estado": "EN_PROCESO"}).status_code, 200)

    def test_la_barra_sigue_marcando_solo_el_calendario(self):
        import re

        html = self.ver(self.gerente, {"estado": "HECHO"}).content.decode()
        self.assertEqual(re.findall(r'<a [^>]*aria-current="page"[^>]*>([^<]*)</a>', html), ["Calendario"])
        self.assertEqual(html.count("<h1"), 1)
