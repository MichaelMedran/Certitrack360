"""SDD del Sprint 3, hito S3-H3: prioridad calculada (RF-42, HU-29). Caso clave 32 de la §13.

Criterio de aceptación: «El orden por defecto pone primero los vencidos y urgentes; cambiar un plazo cambia el nivel sin ninguna
otra acción». La alerta urgente (RF-43) la construye S3-H4: aquí se simula con las costuras `_alerta_abierta` y
`con_alerta_abierta`, y si el modelo `urgencias.AlertaUrgente` ya existe se comprueba también con alertas reales.
"""
import datetime
import itertools
from unittest import mock

from django.apps import apps as registro
from django.db.models import BooleanField, Case, Value, When
from django.test import override_settings
from django.urls import reverse

from apps.clientes.models import Cliente, Contrato
from apps.entregables import filtros, prioridad
from apps.entregables.models import Entregable
from apps.entregables.tests import Base
from apps.entregables.visibilidad import entregables_visibles

E = Entregable.Estado
ALTA, MEDIA, BAJA = prioridad.ALTA, prioridad.MEDIA, prioridad.BAJA


def con_alertas(*ids):
    """Simula alertas urgentes abiertas en los entregables `ids` (hasta que S3-H4 aporte el modelo)."""
    def expresion():
        return Case(When(pk__in=list(ids), then=Value(True)), default=Value(False), output_field=BooleanField())

    return mock.patch.multiple(
        prioridad, _alerta_abierta=expresion, con_alerta_abierta=lambda candidatos: set(ids) & set(candidatos)
    )


class PrioridadBase(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.estrategico = Cliente.objects.create(nombre="Estratégico SA", sector="BANCA", tipo=Cliente.Tipo.ESTRATEGICO)
        cls.ocasional = Cliente.objects.create(nombre="Ocasional SA", sector="PUBLICO", tipo=Cliente.Tipo.OCASIONAL)
        cls.c_est = cls._contrato(cls.estrategico, "CE")
        cls.c_oca = cls._contrato(cls.ocasional, "CO")

    @classmethod
    def _contrato(cls, cliente, numero):
        contrato = Contrato.objects.create(cliente=cliente, numero_contrato=numero, fecha_inicio=datetime.date(2026, 1, 1),
                                           fecha_fin=datetime.date(2027, 1, 1), senior_responsable=cls.s1)
        contrato.juniors.set([cls.j1])
        return contrato

    def entregable(self, contrato, titulo, dias, estado=E.EN_PROCESO):
        return self.nuevo(contrato, self.j1, self.s1, titulo, estado=estado, dias=dias)

    def titulos(self, usuario=None, **params):
        res = filtros.aplicar(entregables_visibles(usuario or self.gerente), params, self.hoy)
        return [e.titulo for e in res.queryset]


class NivelTests(PrioridadBase):
    def nivel(self, dias, tipo, estado=E.EN_PROCESO, alerta=False):
        return prioridad.calcular(self.hoy + datetime.timedelta(days=dias), estado, tipo, alerta, self.hoy)

    def test_vencido_y_critico_son_alta_para_cualquier_cliente(self):
        for tipo in Cliente.Tipo.values:
            for dias in (-30, -1, 0, 1, 2):
                with self.subTest(tipo=tipo, dias=dias):
                    self.assertEqual(self.nivel(dias, tipo), ALTA)

    def test_proximo_es_media_salvo_cliente_estrategico_que_es_alta(self):
        for dias in (3, 5):
            self.assertEqual(self.nivel(dias, Cliente.Tipo.REGULAR), MEDIA)
            self.assertEqual(self.nivel(dias, Cliente.Tipo.OCASIONAL), MEDIA)
            self.assertEqual(self.nivel(dias, Cliente.Tipo.ESTRATEGICO), ALTA)

    def test_normal_es_baja_salvo_estrategico_dentro_de_los_dias_configurados(self):
        self.assertEqual(self.nivel(6, Cliente.Tipo.REGULAR), BAJA)
        self.assertEqual(self.nivel(60, Cliente.Tipo.ESTRATEGICO), BAJA)
        self.assertEqual(self.nivel(6, Cliente.Tipo.ESTRATEGICO), MEDIA)
        self.assertEqual(self.nivel(10, Cliente.Tipo.ESTRATEGICO), MEDIA)
        self.assertEqual(self.nivel(11, Cliente.Tipo.ESTRATEGICO), BAJA)

    @override_settings(PRIORIDAD_DIAS_ESTRATEGICO=20)
    def test_los_dias_del_estrategico_salen_de_la_configuracion(self):
        self.assertEqual(self.nivel(20, Cliente.Tipo.ESTRATEGICO), MEDIA)
        self.assertEqual(self.nivel(21, Cliente.Tipo.ESTRATEGICO), BAJA)

    def test_una_alerta_urgente_abierta_hace_alta_aunque_el_plazo_sea_lejano(self):
        self.assertEqual(self.nivel(60, Cliente.Tipo.OCASIONAL, alerta=True), ALTA)

    def test_un_entregable_entregado_no_tiene_prioridad(self):
        for dias in (-30, 0, 4):
            self.assertIsNone(self.nivel(dias, Cliente.Tipo.ESTRATEGICO, estado=E.HECHO, alerta=True))

    def test_la_condicion_de_base_de_datos_coincide_con_el_calculo(self):
        """Mismo resultado en Python y en SQL para estados, plazos y tipos de cliente, también con alertas."""
        Entregable.objects.all().delete()
        contratos = {Cliente.Tipo.ESTRATEGICO: self.c_est, Cliente.Tipo.REGULAR: self.c1, Cliente.Tipo.OCASIONAL: self.c_oca}
        for (tipo, contrato), estado, dias in itertools.product(contratos.items(), (E.EN_PROCESO, E.HECHO), range(-2, 14)):
            self.entregable(contrato, f"{tipo}-{estado}-{dias}", dias, estado)
        con_alerta = set(Entregable.objects.filter(titulo__endswith="-9").values_list("pk", flat=True))
        with con_alertas(*con_alerta):
            todos = prioridad.enriquecer(Entregable.objects.select_related("contrato__cliente"), self.hoy)
            for nivel in prioridad.ETIQUETAS:
                en_bd = set(prioridad.filtrar(Entregable.objects.all(), nivel, self.hoy).values_list("pk", flat=True))
                en_python = {e.pk for e in todos if e.prioridad == nivel}
                self.assertEqual(en_bd, en_python, nivel)
                self.assertTrue(en_bd, f"la muestra debe incluir {nivel}")
            ordenados = [e.pk for e in prioridad.ordenar(Entregable.objects.all(), self.hoy)]
            self.assertEqual(len(ordenados), len(todos))


class OrdenPorDefectoTests(PrioridadBase):
    """Criterio de aceptación de S3-H3."""

    def test_el_orden_por_defecto_es_prioridad_y_las_opciones_anteriores_se_conservan(self):
        self.assertEqual(filtros.ORDEN_POR_DEFECTO, "prioridad")
        self.assertEqual([v for v, _ in filtros.ORDEN_CHOICES], ["prioridad", "plazo", "urgencia", "cliente"])
        self.assertEqual(filtros.aplicar(entregables_visibles(self.gerente), {}, self.hoy).orden, "prioridad")

    def test_vencidos_y_urgentes_van_primero_y_los_entregados_al_final(self):
        Entregable.objects.all().delete()
        self.entregable(self.c1, "baja", 40)
        self.entregable(self.c1, "media", 4)
        self.entregable(self.c1, "alta-vencido", -3)
        self.entregable(self.c1, "alta-critico", 1)
        self.entregable(self.c1, "entregado", -20, estado=E.HECHO)
        self.entregable(self.c1, "urgente", 40)
        urgente = Entregable.objects.get(titulo="urgente")
        with con_alertas(urgente.pk):
            self.assertEqual(self.titulos(), ["urgente", "alta-vencido", "alta-critico", "media", "baja", "entregado"])

    def test_a_igual_nivel_gana_plazo_luego_tipo_de_cliente_y_id(self):
        Entregable.objects.all().delete()
        self.entregable(self.c1, "regular-d1", 1)
        self.entregable(self.c_oca, "ocasional-d1", 1)
        self.entregable(self.c_est, "estrategico-d1", 1)
        self.entregable(self.c1, "regular-d0", 0)
        self.assertEqual(self.titulos(), ["regular-d0", "estrategico-d1", "regular-d1", "ocasional-d1"])

    def test_el_orden_por_plazo_y_el_de_urgencia_siguen_disponibles(self):
        Entregable.objects.all().delete()
        self.entregable(self.c_est, "est-d1", 1)  # Alta; cliente «Estratégico SA»
        self.entregable(self.c1, "reg-d8", 8)  # Baja; cliente «Cliente Demo» (va antes por nombre)
        self.assertEqual(self.titulos(orden="plazo"), ["est-d1", "reg-d8"])
        self.assertEqual(self.titulos(orden="urgencia"), ["est-d1", "reg-d8"])
        self.assertEqual(self.titulos(orden="cliente"), ["reg-d8", "est-d1"])
        self.assertEqual(self.titulos(orden="valor-raro"), ["est-d1", "reg-d8"])  # no válido: el orden por defecto

    def test_cambiar_un_plazo_cambia_el_nivel_y_el_orden_sin_otra_accion(self):
        Entregable.objects.all().delete()
        a = self.entregable(self.c1, "a", 30)
        b = self.entregable(self.c1, "b", 20)
        self.assertEqual(self.titulos(), ["b", "a"])  # ambos Baja: gana el plazo
        self.assertEqual({e.titulo: e.prioridad for e in prioridad.enriquecer(
            Entregable.objects.select_related("contrato__cliente"), self.hoy)}, {"a": BAJA, "b": BAJA})
        a.plazo = self.hoy - datetime.timedelta(days=1)  # solo se cambia el plazo
        a.save()
        self.assertEqual(self.titulos(), ["a", "b"])
        self.assertEqual(prioridad.enriquecer([Entregable.objects.get(pk=a.pk)], self.hoy)[0].prioridad, ALTA)
        b.plazo = self.hoy + datetime.timedelta(days=4)
        b.save()
        self.assertEqual(prioridad.enriquecer([Entregable.objects.get(pk=b.pk)], self.hoy)[0].prioridad, MEDIA)

    def test_cambiar_el_tipo_de_cliente_cambia_la_prioridad(self):
        e = self.entregable(self.c1, "x", 4)
        self.assertEqual(prioridad.enriquecer([Entregable.objects.get(pk=e.pk)])[0].prioridad, MEDIA)
        Cliente.objects.filter(pk=self.cliente.pk).update(tipo=Cliente.Tipo.ESTRATEGICO)
        self.assertEqual(prioridad.enriquecer([Entregable.objects.get(pk=e.pk)])[0].prioridad, ALTA)

    def test_una_alerta_abierta_sube_el_nivel_y_cerrarla_lo_baja(self):
        Entregable.objects.all().delete()
        lejano = self.entregable(self.c1, "lejano", 40)
        self.entregable(self.c1, "vencido", -1)
        with con_alertas(lejano.pk):
            self.assertEqual(self.titulos(), ["lejano", "vencido"])  # alerta abierta primero dentro de Alta
            self.assertEqual(self.titulos(prioridad="ALTA"), ["lejano", "vencido"])
        self.assertEqual(self.titulos(), ["vencido", "lejano"])  # sin alerta, vuelve a Baja
        self.assertEqual(self.titulos(prioridad="BAJA"), ["lejano"])

    def test_alertas_reales_si_la_app_de_urgencias_ya_las_define(self):
        try:
            modelo = registro.get_model("urgencias", "AlertaUrgente")
            modelo._meta.get_field("cerrada_en")
        except (LookupError, Exception):  # noqa: BLE001  (S3-H4 todavía no la aporta)
            self.skipTest("urgencias.AlertaUrgente aún no existe (S3-H4)")
        self.assertIsNotNone(prioridad._modelo_alerta())


class FiltroPrioridadTests(PrioridadBase):
    def test_filtro_por_nivel_y_chip(self):
        Entregable.objects.all().delete()
        self.entregable(self.c1, "alta", -1)
        self.entregable(self.c1, "media", 4)
        self.entregable(self.c1, "baja", 40)
        self.entregable(self.c1, "hecho", -5, estado=E.HECHO)
        self.assertEqual(self.titulos(prioridad="ALTA"), ["alta"])
        self.assertEqual(self.titulos(prioridad="MEDIA"), ["media"])
        self.assertEqual(self.titulos(prioridad="BAJA"), ["baja"])
        self.assertEqual(len(self.titulos(prioridad="NOPE")), 4)  # valor inválido: se ignora

    def test_el_filtro_no_amplia_la_visibilidad(self):
        Entregable.objects.all().delete()
        propio = self.entregable(self.c1, "propio", -1)
        self.nuevo(self.c2, self.j2, self.s2, "ajeno", estado=E.EN_PROCESO, dias=-1)
        self.assertEqual(self.titulos(self.j1, prioridad="ALTA"), [propio.titulo])


class VistasTests(PrioridadBase):
    def setUp(self):
        Entregable.objects.all().delete()
        self.entregable(self.c1, "Tarea baja", 40)
        self.entregable(self.c1, "Tarea vencida", -2)
        self.entregable(self.c1, "Tarea entregada", -2, estado=E.HECHO)
        self.client.force_login(self.gerente)

    def test_la_lista_y_el_tablero_muestran_la_insignia_con_texto_y_ordenan_por_prioridad(self):
        for nombre in ("entregables", "tablero"):
            with self.subTest(vista=nombre):
                respuesta = self.client.get(reverse(nombre))
                self.assertEqual(respuesta.status_code, 200)
                html = respuesta.content.decode()
                self.assertIn("Prioridad: Alta", html)
                self.assertIn("Prioridad: Baja", html)
                self.assertIn("Sin prioridad (entregado)", html)
                self.assertLess(html.index("Tarea vencida"), html.index("Tarea baja"))
                self.assertIn('<option value="prioridad" selected>', html)

    def test_pedir_el_orden_por_plazo_cambia_el_orden(self):
        html = self.client.get(reverse("entregables"), {"orden": "plazo"}).content.decode()
        self.assertIn('<option value="plazo" selected>', html)

    def test_el_detalle_muestra_la_prioridad(self):
        e = Entregable.objects.get(titulo="Tarea vencida")
        html = self.client.get(reverse("entregable_detalle", args=[e.pk])).content.decode()
        self.assertIn("Prioridad: Alta", html)

    def test_el_inicio_lista_los_pendientes_por_prioridad(self):
        self.client.force_login(self.j1)
        html = self.client.get(reverse("inicio")).content.decode()
        self.assertLess(html.index("Tarea vencida"), html.index("Tarea baja"))
        self.assertIn("Prioridad: Alta", html)
        self.assertNotIn("Tarea entregada", html)  # los entregados no son pendientes

    def test_consultas_constantes_sin_importar_el_numero_de_tarjetas(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def consultas():
            with CaptureQueriesContext(connection) as c:
                self.client.get(reverse("tablero"))
            return len(c)

        base = consultas()
        for i in range(10):
            self.entregable(self.c1, f"extra{i}", i)
        self.assertEqual(consultas(), base)
