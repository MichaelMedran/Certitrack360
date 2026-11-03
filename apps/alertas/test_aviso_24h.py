"""SDD del Sprint 2, hito S2-H1 · RF-22 (caso 15): con los umbrales 5,2,1,0 se suma el aviso de 24 horas, que sale una
sola vez por entregable y destinatario, y la urgencia «Crítico» sigue empezando a 2 días (segundo umbral mayor)."""
import datetime
import itertools
import os
import runpy
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, override_settings

from apps.alertas.models import Notificacion
from apps.alertas.servicios import generar_alertas, texto_vencimiento
from apps.entregables import urgencia
from apps.entregables.models import Entregable
from apps.entregables.tests import Base

E = Entregable.Estado
CON_24_HORAS = [5, 2, 1, 0]


@override_settings(ALERT_THRESHOLDS_DAYS=CON_24_HORAS)
class AvisoDe24HorasTests(Base):
    def umbrales_de(self, entregable, usuario):
        return sorted(Notificacion.objects.filter(entregable=entregable, usuario=usuario, tipo="VENCIMIENTO")
                      .values_list("umbral", flat=True))

    def test_el_aviso_de_24_horas_sale_una_sola_vez_aunque_la_tarea_corra_varias_veces(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Mañana", dias=1)
        self.assertEqual(generar_alertas(self.hoy), 2)  # junior y senior revisor
        for _ in range(3):
            self.assertEqual(generar_alertas(self.hoy), 0)
        for usuario in (self.j1, self.s1):
            self.assertEqual(self.umbrales_de(e, usuario), [1])

    def test_a_lo_largo_de_los_dias_sale_un_aviso_por_umbral_incluido_el_de_24_horas(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Seguimiento", dias=6)
        for avance in range(0, 8):
            generar_alertas(self.hoy + datetime.timedelta(days=avance))
        for usuario in (self.j1, self.s1):
            self.assertEqual(self.umbrales_de(e, usuario), [0, 1, 2, 5])  # 5 días, 48 h, 24 h y el día del plazo

    def test_la_base_de_datos_impide_un_segundo_aviso_de_24_horas(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Mañana", dias=1)
        generar_alertas(self.hoy)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Notificacion.objects.create(usuario=self.j1, entregable=e, tipo="VENCIMIENTO", umbral=1, mensaje="otra vez")

    def test_el_aviso_dice_manana_y_lleva_el_codigo(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Informe técnico 03", dias=1)
        generar_alertas(self.hoy)
        n = Notificacion.objects.get(entregable=e, usuario=self.j1)
        self.assertEqual(n.mensaje, f"{e.codigo} «Informe técnico 03» vence mañana, el {e.plazo:%d/%m/%Y}.")

    def test_los_entregados_y_los_vencidos_no_reciben_el_aviso(self):
        self.nuevo(self.c1, self.j1, self.s1, "Entregado", estado=E.HECHO, dias=1)
        self.nuevo(self.c1, self.j1, self.s1, "Vencido", dias=-1)
        self.assertEqual(generar_alertas(self.hoy), 0)

    def test_critico_sigue_empezando_a_2_dias(self):
        self.assertEqual(urgencia.umbrales(), (2, 5))
        esperado = {-1: "VENCIDO", 0: "CRITICO", 1: "CRITICO", 2: "CRITICO", 3: "PROXIMO", 5: "PROXIMO", 6: "NORMAL"}
        for dias, valor in esperado.items():
            with self.subTest(dias=dias):
                self.assertEqual(urgencia.calcular(self.hoy + datetime.timedelta(days=dias), E.EN_PROCESO, self.hoy), valor)

    def test_la_condicion_de_base_de_datos_coincide_con_el_calculo(self):
        Entregable.objects.all().delete()
        for estado, dias in itertools.product(E.values, range(-2, 8)):
            self.nuevo(self.c1, self.j1, self.s1, f"{estado}{dias}", estado=estado, dias=dias)
        todos = list(Entregable.objects.all())
        for valor in urgencia.ETIQUETAS:
            en_bd = set(Entregable.objects.filter(urgencia.condicion(valor, self.hoy)).values_list("pk", flat=True))
            en_python = {e.pk for e in todos if urgencia.calcular(e.plazo, e.estado, self.hoy) == valor}
            self.assertEqual(en_bd, en_python, valor)


class SegundoUmbralMayorTests(SimpleTestCase):
    """«Crítico» = segundo umbral mayor de los positivos; con uno solo, ese (así se conserva lo del Sprint 1)."""

    CASOS = {
        (5, 2, 1, 0): (2, 5), (5, 2, 0): (2, 5), (0, 1, 2, 5): (2, 5), (7, 3, 0): (3, 7), (10, 4, 1, 0): (4, 10),
        (10, 4, 0): (4, 10), (10, 0): (10, 10), (1, 0): (1, 1), (3,): (3, 3), (0,): (0, 0), (5, 5, 2, 2, 1, 0): (2, 5),
    }

    def test_casos(self):
        for config, esperado in self.CASOS.items():
            with self.subTest(config=config), override_settings(ALERT_THRESHOLDS_DAYS=list(config)):
                self.assertEqual(urgencia.umbrales(), esperado)


class TextoDelAvisoTests(Base):
    def test_hoy_manana_y_en_n_dias(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Acta", dias=3)
        self.assertEqual(texto_vencimiento(e, 0), f"{e.codigo} «Acta» vence hoy.")
        self.assertEqual(texto_vencimiento(e, 1), f"{e.codigo} «Acta» vence mañana, el {e.plazo:%d/%m/%Y}.")
        self.assertEqual(texto_vencimiento(e, 3), f"{e.codigo} «Acta» vence en 3 días, el {e.plazo:%d/%m/%Y}.")


def umbrales_por_defecto():
    """ALERT_THRESHOLDS_DAYS que deja settings.py cuando el entorno (ni un archivo .env) no la define."""
    original = Path.exists

    def exists(ruta, *args, **kwargs):
        return False if ruta.name == ".env" else original(ruta, *args, **kwargs)

    entorno = {k: v for k, v in os.environ.items() if k != "ALERT_THRESHOLDS_DAYS"}
    with mock.patch.dict(os.environ, entorno, clear=True), mock.patch.object(Path, "exists", exists):
        return runpy.run_path(str(Path(settings.BASE_DIR) / "certitrack" / "settings.py"))["ALERT_THRESHOLDS_DAYS"]


class ConfiguracionDeUmbralesTests(SimpleTestCase):
    def test_el_ejemplo_de_entorno_documenta_el_aviso_de_24_horas_y_el_prefijo(self):
        ejemplo = (Path(settings.BASE_DIR) / ".env.example").read_text(encoding="utf-8")
        self.assertIn("ALERT_THRESHOLDS_DAYS=5,2,1,0\n", ejemplo)
        self.assertNotIn("ALERT_THRESHOLDS_DAYS=5,2,0\n", ejemplo)
        self.assertIn("CODIGO_PREFIJO=CT", ejemplo)
        self.assertEqual(settings.CODIGO_PREFIJO, "CT")

    def test_el_valor_por_defecto_es_5_2_1_0(self):
        # SDD del Sprint 2, §10.1 y RF-22 (aprobado en la §15).
        self.assertEqual(umbrales_por_defecto(), [5, 2, 1, 0])


class ValorPorDefectoTests(Base):
    """Caso 15 con el valor por defecto de settings.py (no con uno fijado a mano)."""

    def test_con_el_valor_por_defecto_critico_empieza_a_2_dias_y_el_aviso_de_24_h_sale_una_vez(self):
        with override_settings(ALERT_THRESHOLDS_DAYS=umbrales_por_defecto()):
            self.assertEqual(urgencia.umbrales(), (2, 5))
            self.assertEqual(urgencia.calcular(self.hoy + datetime.timedelta(days=2), E.EN_PROCESO, self.hoy), "CRITICO")
            self.assertEqual(urgencia.calcular(self.hoy + datetime.timedelta(days=3), E.EN_PROCESO, self.hoy), "PROXIMO")
            e = self.nuevo(self.c1, self.j1, self.s1, "Por defecto", dias=6)
            for avance in range(0, 8):
                for _ in range(2):  # la tarea puede correr más de una vez al día
                    generar_alertas(self.hoy + datetime.timedelta(days=avance))
            for usuario in (self.j1, self.s1):
                umbrales = list(Notificacion.objects.filter(entregable=e, usuario=usuario, tipo="VENCIMIENTO")
                                .values_list("umbral", flat=True))
                self.assertEqual(sorted(umbrales), [0, 1, 2, 5])
                self.assertEqual(umbrales.count(1), 1)
