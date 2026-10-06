"""Pruebas de urgencia, filtros y orden (SDD RF-15, caso 10 de la sección 17.2)."""
import datetime
import itertools

from django.test import override_settings
from django.urls import reverse

from apps.clientes.models import Cliente, Contrato
from apps.entregables import filtros, urgencia
from apps.entregables.models import Entregable, Observacion
from apps.entregables.tests import Base
from apps.entregables.visibilidad import entregables_visibles

E = Entregable.Estado


class UrgenciaTests(Base):
    def dias(self, n, estado=E.EN_PROCESO):
        return urgencia.calcular(self.hoy + datetime.timedelta(days=n), estado, self.hoy)

    def test_umbrales_por_defecto(self):
        esperado = {-30: "VENCIDO", -1: "VENCIDO", 0: "CRITICO", 1: "CRITICO", 2: "CRITICO",
                    3: "PROXIMO", 5: "PROXIMO", 6: "NORMAL", 60: "NORMAL"}
        for dias, valor in esperado.items():
            with self.subTest(dias=dias):
                self.assertEqual(self.dias(dias), valor)

    def test_un_entregable_hecho_nunca_corre_contra_el_plazo(self):
        for dias in (-30, 0, 1, 4):
            with self.subTest(dias=dias):
                self.assertEqual(self.dias(dias, E.HECHO), "NORMAL")

    def test_listo_para_entrega_si_corre_contra_el_plazo(self):
        self.assertEqual(self.dias(-1, E.LISTO_PARA_ENTREGA), "VENCIDO")

    @override_settings(ALERT_THRESHOLDS_DAYS=[7, 3, 0])
    def test_respeta_los_umbrales_configurados(self):
        self.assertEqual(self.umbrales(), (3, 7))
        esperado = {-1: "VENCIDO", 0: "CRITICO", 3: "CRITICO", 4: "PROXIMO", 7: "PROXIMO", 8: "NORMAL"}
        for dias, valor in esperado.items():
            with self.subTest(dias=dias):
                self.assertEqual(self.dias(dias), valor)

    @override_settings(ALERT_THRESHOLDS_DAYS=[10, 0])
    def test_con_un_solo_umbral_positivo_no_hay_proximo(self):
        self.assertEqual(self.umbrales(), (10, 10))
        self.assertEqual(self.dias(10), "CRITICO")
        self.assertEqual(self.dias(11), "NORMAL")

    @override_settings(ALERT_THRESHOLDS_DAYS=[0])
    def test_solo_el_dia_del_vencimiento(self):
        self.assertEqual(self.dias(0), "CRITICO")
        self.assertEqual(self.dias(1), "NORMAL")

    def umbrales(self):
        return urgencia.umbrales()

    def test_propiedad_del_modelo(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Pronto", dias=1)
        self.assertEqual((e.urgencia, e.urgencia_etiqueta), ("CRITICO", "Crítico"))
        e.plazo = self.hoy - datetime.timedelta(days=1)
        self.assertEqual(e.urgencia_etiqueta, "Vencido")

    def test_la_condicion_de_base_de_datos_coincide_con_el_calculo(self):
        """Mismo resultado en Python y en SQL, para varios estados, plazos y configuraciones."""
        for config in ([5, 2, 0], [7, 3, 0], [10, 0], [0]):
            with override_settings(ALERT_THRESHOLDS_DAYS=config):
                Entregable.objects.exclude(pk__in=[self.e1.pk, self.e2.pk]).delete()
                for estado, dias in itertools.product(E.values, range(-3, 13)):
                    self.nuevo(self.c1, self.j1, self.s1, f"{estado}{dias}", estado=estado, dias=dias)
                todos = list(Entregable.objects.all())
                for valor in urgencia.ETIQUETAS:
                    en_bd = set(Entregable.objects.filter(urgencia.condicion(valor, self.hoy)).values_list("pk", flat=True))
                    en_python = {e.pk for e in todos if urgencia.calcular(e.plazo, e.estado, self.hoy) == valor}
                    self.assertEqual(en_bd, en_python, f"{valor} con {config}")


class FiltrosBase(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.cliente2 = Cliente.objects.create(nombre="Segundo Cliente", sector="TELECOM")
        cls.c3 = Contrato.objects.create(
            cliente=cls.cliente2, numero_contrato="C3", fecha_inicio=datetime.date(2026, 1, 1),
            fecha_fin=datetime.date(2027, 1, 1), senior_responsable=cls.s1)
        cls.c3.juniors.set([cls.j1, cls.j2])
        cls.a = cls.nuevo(cls.c1, cls.j1, cls.s1, "a-vencido", E.EN_PROCESO, -3)
        cls.b = cls.nuevo(cls.c1, cls.j1, cls.s1, "b-hoy", E.EN_PROCESO, 0)
        cls.c = cls.nuevo(cls.c3, cls.j1, cls.s1, "c-critico", E.EN_PROCESO, 2)
        cls.d = cls.nuevo(cls.c3, cls.j2, cls.s1, "d-proximo", E.VERIFICACION_SENIOR, 4)
        cls.f = cls.nuevo(cls.c2, cls.j2, cls.s2, "f-proximo", E.LISTO_PARA_ENTREGA, 5)
        cls.g = cls.nuevo(cls.c1, cls.j1, cls.s1, "g-hecho", E.HECHO, -20)
        cls.h = cls.nuevo(cls.c2, cls.j2, cls.s2, "h-vencido", E.EN_PROCESO, -1)
        obs = lambda e, tipo, resuelta: Observacion.objects.create(
            entregable=e, autor=cls.s1, tipo_error=tipo, descripcion="x", resuelta=resuelta,
            solucion="ok" if resuelta else "")
        obs(cls.a, "FORMATO", False)
        obs(cls.b, "FORMATO", True)
        obs(cls.c, "CONTENIDO", False)
        obs(cls.d, "FORMATO", True)
        obs(cls.d, "CONTENIDO", False)
        obs(cls.f, "FORMATO", False)
        obs(cls.f, "FORMATO", True)

    def ver(self, usuario, **params):
        res = filtros.aplicar(entregables_visibles(usuario), params, self.hoy)
        return [e.titulo for e in res.queryset]

    def ver_set(self, usuario, **params):
        return set(self.ver(usuario, **params))


class FiltrosTests(FiltrosBase):
    def test_sin_filtros_se_ve_todo_lo_visible_ordenado_por_plazo(self):
        self.assertEqual(self.ver(self.j1), ["g-hecho", "a-vencido", "b-hoy", "c-critico", "E1"])
        self.assertEqual(self.ver_set(self.gerente), {e.titulo for e in Entregable.objects.all()})

    def test_cada_filtro_por_separado(self):
        self.assertEqual(self.ver_set(self.gerente, cliente=self.cliente2.pk), {"c-critico", "d-proximo"})
        self.assertEqual(self.ver_set(self.gerente, contrato=self.c2.pk), {"E2", "f-proximo", "h-vencido"})
        self.assertEqual(self.ver_set(self.gerente, estado="EN_PROCESO"), {"a-vencido", "b-hoy", "c-critico", "h-vencido"})
        self.assertEqual(self.ver_set(self.gerente, urgencia="VENCIDO"), {"a-vencido", "h-vencido"})
        self.assertEqual(self.ver_set(self.gerente, urgencia="CRITICO"), {"b-hoy", "c-critico"})
        self.assertEqual(self.ver_set(self.gerente, urgencia="PROXIMO"), {"d-proximo", "f-proximo"})
        self.assertEqual(self.ver_set(self.gerente, urgencia="NORMAL"), {"E1", "E2", "g-hecho"})

    def test_filtro_por_responsable_cuenta_junior_y_senior(self):
        self.assertEqual(self.ver_set(self.gerente, responsable=self.j2.pk), {"E2", "d-proximo", "f-proximo", "h-vencido"})
        self.assertEqual(self.ver_set(self.gerente, responsable=self.s2.pk), {"E2", "f-proximo", "h-vencido"})

    def test_filtros_combinados(self):
        self.assertEqual(self.ver_set(self.gerente, cliente=self.cliente.pk, urgencia="VENCIDO"), {"a-vencido", "h-vencido"})
        self.assertEqual(self.ver_set(self.gerente, cliente=self.cliente2.pk, estado="EN_PROCESO"), {"c-critico"})

    def test_tipo_de_observacion_solo_cuenta_las_no_resueltas(self):
        self.assertEqual(self.ver_set(self.gerente, tipo_observacion="FORMATO"), {"a-vencido", "f-proximo"})
        self.assertEqual(self.ver_set(self.gerente, tipo_observacion="CONTENIDO"), {"c-critico", "d-proximo"})
        self.assertEqual(self.ver_set(self.gerente, tipo_observacion="PLAZO"), set())
        # b solo tiene un FORMATO resuelto y d lo tiene resuelto (y un CONTENIDO abierto): no entran por FORMATO.
        self.assertNotIn("b-hoy", self.ver_set(self.gerente, tipo_observacion="FORMATO"))
        self.assertNotIn("d-proximo", self.ver_set(self.gerente, tipo_observacion="FORMATO"))

    def test_resolver_la_observacion_saca_al_entregable_del_filtro(self):
        Observacion.objects.filter(entregable=self.a).update(resuelta=True, solucion="listo")
        self.assertNotIn("a-vencido", self.ver_set(self.gerente, tipo_observacion="FORMATO"))

    def test_valores_no_validos_se_ignoran(self):
        res = filtros.aplicar(entregables_visibles(self.gerente), {
            "cliente": "abc", "contrato": "", "responsable": "1; DROP", "estado": "XYZ", "urgencia": "NOPE",
            "tipo_observacion": "MALO", "orden": "hack"}, self.hoy)
        self.assertEqual(res.activos, {})
        self.assertEqual(res.orden, "plazo")
        self.assertEqual(res.queryset.count(), Entregable.objects.count())


class OrdenTests(FiltrosBase):
    def test_orden_por_urgencia(self):
        self.assertEqual(
            self.ver(self.gerente, orden="urgencia"),
            ["a-vencido", "h-vencido", "b-hoy", "c-critico", "d-proximo", "f-proximo", "E1", "E2", "g-hecho"],
        )

    def test_los_hechos_van_al_final_aunque_su_plazo_sea_viejo(self):
        self.assertEqual(self.ver(self.gerente, orden="urgencia")[-1], "g-hecho")

    def test_orden_por_cliente_y_luego_plazo(self):
        titulos = self.ver(self.gerente, orden="cliente")
        # «Cliente Demo» antes que «Segundo Cliente»; dentro de cada uno, por plazo.
        self.assertEqual(titulos[-2:], ["c-critico", "d-proximo"])
        self.assertEqual(titulos[0], "g-hecho")

    def test_orden_por_defecto_es_el_plazo(self):
        titulos = self.ver(self.gerente)
        plazos = [Entregable.objects.get(titulo=t).plazo for t in titulos]
        self.assertEqual(plazos, sorted(plazos))

    def test_el_orden_se_combina_con_los_filtros(self):
        self.assertEqual(self.ver(self.gerente, estado="EN_PROCESO", orden="urgencia"),
                         ["a-vencido", "h-vencido", "b-hoy", "c-critico"])


class VisibilidadTests(FiltrosBase):
    """Los filtros nunca amplían lo que el usuario puede ver."""

    def test_junior_filtrando_por_un_cliente_que_no_tiene_no_ve_nada(self):
        self.assertEqual(self.ver(self.j2, cliente=self.cliente.pk, contrato=self.c1.pk), [])
        # j1 no tiene nada en el contrato c2
        self.assertEqual(self.ver(self.j1, contrato=self.c2.pk), [])

    def test_junior_filtrando_por_un_responsable_ajeno_no_ve_nada(self):
        self.assertEqual(self.ver(self.j1, responsable=self.j2.pk), [])
        self.assertEqual(self.ver(self.j1, responsable=self.s2.pk), [])

    def test_senior_no_ve_los_contratos_de_otro(self):
        self.assertEqual(self.ver(self.s1, contrato=self.c2.pk), [])
        self.assertEqual(self.ver(self.s2, cliente=self.cliente2.pk), [])

    def test_ninguna_combinacion_devuelve_algo_fuera_de_lo_visible(self):
        usuarios = (self.j1, self.j2, self.s1, self.s2, self.gerente, self.admin)
        valores = {  # cliente, contrato y responsable son los vectores de ampliación; el resto, un representante
            "cliente": [None, self.cliente.pk, self.cliente2.pk],
            "contrato": [None, self.c1.pk, self.c2.pk, self.c3.pk],
            "responsable": [None, self.j1.pk, self.s2.pk],
            "estado": [None, "EN_PROCESO"],
            "urgencia": [None, "VENCIDO"],
            "tipo_observacion": [None, "FORMATO"],
        }
        claves = list(valores)
        for usuario in usuarios:
            visibles = set(entregables_visibles(usuario).values_list("pk", flat=True))
            for combinacion in itertools.product(*valores.values()):
                params = {k: v for k, v in zip(claves, combinacion) if v is not None}
                for orden in ("plazo", "urgencia", "cliente"):
                    if orden != "plazo" and len(params) > 1:
                        continue  # el orden no puede ampliar nada; basta probarlo con pocos filtros
                    res = filtros.aplicar(entregables_visibles(usuario), {**params, "orden": orden}, self.hoy)
                    obtenidos = set(res.queryset.values_list("pk", flat=True))
                    self.assertLessEqual(obtenidos, visibles, f"{usuario.username} {params} {orden}")

    def test_las_opciones_de_los_filtros_solo_muestran_lo_visible(self):
        o = filtros.opciones(self.j2)
        self.assertEqual({c.nombre for c in o["clientes"]}, {"Cliente Demo", "Segundo Cliente"})
        self.assertEqual({c.numero_contrato for c in o["contratos"]}, {"C2", "C3"})
        self.assertNotIn(self.j1, o["responsables"])
        o1 = filtros.opciones(self.j1)
        self.assertEqual({c.numero_contrato for c in o1["contratos"]}, {"C1", "C3"})
        self.assertEqual({u.username for u in o1["responsables"]}, {"j1", "s1"})

    def test_las_opciones_del_gerente_incluyen_todo(self):
        o = filtros.opciones(self.gerente)
        self.assertEqual({c.numero_contrato for c in o["contratos"]}, {"C1", "C2", "C3"})
        self.assertEqual({u.username for u in o["responsables"]}, {"j1", "j2", "s1", "s2"})


class FiltrosEnLasVistasTests(FiltrosBase):
    def test_la_lista_aplica_los_filtros_de_la_url(self):
        self.client.force_login(self.gerente)
        r = self.client.get(reverse("entregables"), {"urgencia": "VENCIDO", "orden": "urgencia"})
        self.assertEqual([e.titulo for e in r.context["entregables"]], ["a-vencido", "h-vencido"])
        self.assertEqual(r.context["filtros_activos"], {"urgencia": "VENCIDO"})

    def test_la_lista_sigue_aceptando_el_filtro_de_estado(self):
        self.client.force_login(self.j1)
        r = self.client.get(reverse("entregables"), {"estado": "EN_PROCESO"})
        self.assertEqual(r.context["filtros_activos"], {"estado": "EN_PROCESO"})
        self.assertEqual({e.titulo for e in r.context["entregables"]}, {"a-vencido", "b-hoy", "c-critico"})

    def test_la_lista_de_un_junior_con_cliente_ajeno_queda_vacia(self):
        self.client.force_login(self.j1)
        r = self.client.get(reverse("entregables"), {"cliente": self.cliente2.pk, "contrato": self.c2.pk})
        self.assertEqual(list(r.context["entregables"]), [])

    def test_el_tablero_aplica_los_filtros_y_el_orden(self):
        self.client.force_login(self.s1)
        r = self.client.get(reverse("tablero"), {"tipo_observacion": "CONTENIDO", "orden": "urgencia"})
        por_columna = {c["valor"]: [e.titulo for e in c["tarjetas"]] for c in r.context["columnas"]}
        self.assertEqual(por_columna["EN_PROCESO"], ["c-critico"])
        self.assertEqual(por_columna["VERIFICACION_SENIOR"], ["d-proximo"])
        self.assertEqual(sum(len(v) for v in por_columna.values()), 2)

    def test_el_tablero_de_un_junior_no_filtra_fuera_de_lo_suyo(self):
        self.client.force_login(self.j1)
        r = self.client.get(reverse("tablero"), {"responsable": self.j2.pk})
        self.assertEqual(sum(len(c["tarjetas"]) for c in r.context["columnas"]), 0)

    def test_las_paginas_siguen_respondiendo_con_cualquier_parametro(self):
        self.client.force_login(self.gerente)
        for nombre in ("entregables", "tablero"):
            r = self.client.get(reverse(nombre), {"cliente": "x", "estado": "ZZZ", "orden": "<script>"})
            self.assertEqual(r.status_code, 200)
