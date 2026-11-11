"""Auditoría S3-H1 de HU-13 (indicadores de desempeño, RF-33): un caso por criterio de Trello, de punta a punta en pantalla.

La lógica de cálculo ya la cubre `tests.py` (caso 24); aquí se comprueba lo que ve el usuario en `/indicadores/`.
"""
import datetime
import re

from django.urls import reverse

from apps.clientes.models import Cliente, PlantillaTDR
from apps.entregables.models import Adjunto, Entrega, Entregable, HistorialEstado, Observacion, TipoError
from apps.entregables.tests import Base
from apps.entregables.tipos import TipoAdjunto

E = Entregable.Estado


class AuditoriaHU13Tests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Entregable.objects.all().delete()
        cls.cliente_otro = Cliente.objects.create(nombre="Cliente Otro", sector="TELECOM")
        cls.c2.cliente = cls.cliente_otro
        cls.c2.save()
        cls.plantilla_b = PlantillaTDR.objects.create(
            nombre="Plantilla B", campos_requeridos=[{"nombre": "c_x", "etiqueta": "X", "tipo": "texto"}]
        )
        # A (c1, j1, plantilla P): entregado a tiempo (recepción 01/10, entrega 06/10, plazo 10/10), 2 obs de formato.
        cls.a = cls._hecho(cls.c1, cls.j1, cls.s1, cls.plantilla, "A", datetime.date(2026, 10, 1),
                           datetime.date(2026, 10, 10), datetime.date(2026, 10, 6))
        # B (c2, j2, plantilla B): entregado tarde (recepción 01/11, entrega 15/11, plazo 10/11) con devolución, 1 obs de contenido.
        cls.b = cls._hecho(cls.c2, cls.j2, cls.s2, cls.plantilla_b, "B", datetime.date(2026, 11, 1),
                           datetime.date(2026, 11, 10), datetime.date(2026, 11, 15))
        HistorialEstado.objects.create(entregable=cls.b, estado_anterior=E.VERIFICACION_SENIOR,
                                       estado_nuevo=E.EN_PROCESO, usuario=cls.s2, detalle="Devuelto")
        for desc in ("uno", "dos"):
            Observacion.objects.create(entregable=cls.a, autor=cls.s1, responsable=cls.j1,
                                       tipo_error=TipoError.FORMATO, descripcion=desc)
        Observacion.objects.create(entregable=cls.b, autor=cls.s2, responsable=cls.j2,
                                   tipo_error=TipoError.CONTENIDO, descripcion="tres")

    @classmethod
    def _hecho(cls, contrato, junior, senior, plantilla, titulo, recepcion, plazo, entrega):
        e = Entregable.objects.create(
            contrato=contrato, plantilla=plantilla, titulo=titulo, id_tdr="T-" + titulo, fecha_recepcion=recepcion,
            plazo=plazo, datos={}, estado=E.HECHO, junior_asignado=junior, senior_revisor=senior, creado_por=senior)
        mk = lambda tipo, nombre: Adjunto.objects.create(
            entregable=e, archivo="demo/" + nombre, nombre_original=nombre, tipo=tipo, version=1,
            subido_por=senior, bloqueado=True)
        Entrega.objects.create(entregable=e, numero=1, fecha_entrega=entrega, medio=Entrega.Medio.CORREO,
                               cargo=mk(TipoAdjunto.CARGO_RECEPCION, "cargo.pdf"),
                               version_enviada=mk(TipoAdjunto.VERSION_FINAL, "vf.pdf"), registrada_por=senior)
        return e

    def _panel(self, usuario, **params):
        self.client.force_login(usuario)
        r = self.client.get(reverse("indicadores"), params)
        self.assertEqual(r.status_code, 200)
        return r

    def test_criterio_1_el_panel_muestra_los_cuatro_indicadores_minimos(self):
        """Criterio 1: % a tiempo, % con reproceso, tiempo promedio por tipo y observaciones por tipo de error."""
        r = self._panel(self.gerente)
        for texto in ("Entregados a tiempo", "Con reproceso", "Tiempo promedio de elaboración",
                      "Tiempo promedio por tipo de entregable", "Observaciones por tipo de error"):
            self.assertContains(r, texto)
        self.assertEqual(r.context["a_tiempo_pct"], 50)      # A a tiempo, B tarde
        self.assertEqual(r.context["reproceso_pct"], 50)     # solo B tuvo devolución, ambos pasaron por revisión
        filas = {f["nombre"]: f["dias_promedio"] for f in r.context["por_plantilla"]}
        self.assertEqual(filas, {self.plantilla.nombre: 5.0, "Plantilla B": 14.0})
        tipos = {f["tipo_error"]: f["cantidad"] for f in r.context["por_tipo_error"]}
        self.assertEqual(tipos, {TipoError.FORMATO: 2, TipoError.CONTENIDO: 1})
        self.assertContains(r, "Formato")
        self.assertContains(r, "Contenido")

    def test_criterio_2_el_calculo_es_automatico_sin_ingreso_manual(self):
        """Criterio 2: la pantalla no ofrece capturar cifras (solo un formulario GET de filtros) y se recalcula sola."""
        html = self._panel(self.gerente).content.decode()
        formularios = re.findall(r"<form[^>]*>", html)
        propios = [f for f in formularios if reverse("indicadores") in f]
        self.assertEqual(len(propios), 1)
        self.assertIn('method="get"', propios[0])
        # Los únicos campos de la pantalla son los filtros (fechas y listas); ninguno captura una cifra.
        self.assertEqual(set(re.findall(r'<input[^>]*type="(\w+)"', html.split("<main", 1)[-1])), {"date"})
        # Un dato nuevo cambia la cifra sin ninguna otra acción.
        Observacion.objects.create(entregable=self.a, autor=self.s1, responsable=self.j1,
                                   tipo_error=TipoError.PLAZO, descripcion="cuatro")
        self.assertEqual(self._panel(self.gerente).context["observaciones_total"], 4)

    def test_criterio_3_filtros_por_periodo_cliente_tipo_y_responsable(self):
        """Criterio 3: filtros por periodo, cliente, tipo de entregable y responsable."""
        html = self._panel(self.gerente).content.decode()
        for nombre in ("desde", "hasta", "cliente", "plantilla", "responsable"):
            self.assertIn(f'name="{nombre}"', html)
        r = self._panel(self.gerente, desde="2026-11-01")
        self.assertEqual((r.context["entregados_total"], r.context["a_tiempo_pct"]), (1, 0))
        r = self._panel(self.gerente, hasta="2026-10-31")
        self.assertEqual((r.context["entregados_total"], r.context["a_tiempo_pct"]), (1, 100))
        r = self._panel(self.gerente, cliente=self.cliente_otro.pk)
        self.assertEqual(r.context["entregados_total"], 1)
        self.assertEqual(r.context["observaciones_total"], 1)
        r = self._panel(self.gerente, plantilla=self.plantilla.pk)
        self.assertEqual(r.context["observaciones_total"], 2)
        r = self._panel(self.gerente, responsable=self.j2.pk)
        self.assertEqual(r.context["entregados_total"], 1)
        self.assertEqual(r.context["a_tiempo_pct"], 0)
        self.assertContains(r, "Responsable: ")

    def test_criterio_4_cada_indicador_muestra_su_formula(self):
        """Criterio 4: fórmula o explicación visible en cada indicador."""
        r = self._panel(self.gerente)
        self.assertContains(r, "¿Cómo se calcula?", count=4)
        for formula in ("≤ plazo", "devolución", "días entre la creación y la entrega", "por tipo de error"):
            self.assertContains(r, formula)

    def test_criterio_5_senior_y_junior_solo_ven_lo_suyo(self):
        """Criterio 5: el senior ve los indicadores de sus proyectos y el junior los suyos (nunca los ajenos)."""
        r = self._panel(self.s1)
        self.assertEqual(r.context["entregados_total"], 1)
        self.assertEqual({f["tipo_error"] for f in r.context["por_tipo_error"]}, {TipoError.FORMATO})
        self.assertNotContains(r, "Cliente Otro")
        r = self._panel(self.j2)
        self.assertEqual(r.context["entregados_total"], 1)
        self.assertEqual({f["tipo_error"] for f in r.context["por_tipo_error"]}, {TipoError.CONTENIDO})
        self.assertNotContains(r, "Demo")
        # Forzar el filtro de lo ajeno no amplía la visibilidad.
        r = self._panel(self.j2, cliente=self.cliente.pk)
        self.assertEqual(r.context["entregados_total"], 0)
