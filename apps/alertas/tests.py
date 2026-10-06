"""Pruebas de notificaciones y tareas programadas (SDD RF-13, RF-14; caso 9 de la sección 17.2)."""
import datetime
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse

from apps.alertas import programador
from apps.alertas.models import Notificacion
from apps.alertas.servicios import generar_alertas
from apps.entregables.models import Entregable
from apps.entregables.tests import Base

E = Entregable.Estado


class LecturaTests(Base):
    def setUp(self):
        self.n1 = Notificacion.objects.create(usuario=self.j1, entregable=self.e1, tipo="ASIGNACION", mensaje="uno")
        self.n2 = Notificacion.objects.create(usuario=self.j1, entregable=self.e1, tipo="OBSERVACION", mensaje="dos")
        self.ajena = Notificacion.objects.create(usuario=self.j2, entregable=self.e2, tipo="ASIGNACION", mensaje="otra")

    def test_ruta_del_sdd(self):
        self.assertEqual(reverse("notificacion_leer", args=[5]), "/notificaciones/5/leer/")

    def test_marcar_una_como_leida(self):
        self.client.force_login(self.j1)
        r = self.client.post(reverse("notificacion_leer", args=[self.n1.pk]))
        self.assertRedirects(r, reverse("notificaciones"))
        self.n1.refresh_from_db()
        self.n2.refresh_from_db()
        self.assertTrue(self.n1.leida)
        self.assertFalse(self.n2.leida)

    def test_el_indicador_de_no_leidas_baja(self):
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(reverse("inicio")).context["no_leidas"], 2)
        self.client.post(reverse("notificacion_leer", args=[self.n1.pk]))
        self.assertEqual(self.client.get(reverse("inicio")).context["no_leidas"], 1)

    def test_no_se_puede_marcar_la_de_otra_persona(self):
        self.client.force_login(self.j1)
        self.assertEqual(self.client.post(reverse("notificacion_leer", args=[self.ajena.pk])).status_code, 404)
        self.ajena.refresh_from_db()
        self.assertFalse(self.ajena.leida)

    def test_marcar_requiere_post(self):
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(reverse("notificacion_leer", args=[self.n1.pk])).status_code, 405)

    def test_marcar_todas_solo_afecta_a_las_propias(self):
        self.client.force_login(self.j1)
        self.client.post(reverse("notificaciones_leidas"))
        self.assertFalse(Notificacion.objects.filter(usuario=self.j1, leida=False).exists())
        self.ajena.refresh_from_db()
        self.assertFalse(self.ajena.leida)

    def test_cada_persona_ve_solo_las_suyas(self):
        self.client.force_login(self.j1)
        mensajes = {n.mensaje for n in self.client.get(reverse("notificaciones")).context["notificaciones"]}
        self.assertEqual(mensajes, {"uno", "dos"})


class AlertasDeVencimientoTests(Base):
    def test_una_sola_por_destinatario_y_umbral_tambien_en_la_base_de_datos(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Pronto", dias=2)
        generar_alertas(self.hoy)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Notificacion.objects.create(usuario=self.j1, entregable=e, tipo="VENCIMIENTO", umbral=2, mensaje="duplicada")

    def test_destinatarios_son_el_junior_y_el_senior_revisor(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Pronto", dias=1)
        generar_alertas(self.hoy)
        self.assertEqual({n.usuario for n in Notificacion.objects.filter(entregable=e)}, {self.j1, self.s1})

    def test_recorre_los_entregables_no_cerrados(self):
        self.nuevo(self.c1, self.j1, self.s1, "Cerrado", estado=E.HECHO, dias=1)
        listo = self.nuevo(self.c1, self.j1, self.s1, "Listo", estado=E.LISTO_PARA_ENTREGA, dias=1)
        generar_alertas(self.hoy)
        self.assertEqual({n.entregable for n in Notificacion.objects.all()}, {listo})

    @override_settings(ALERT_THRESHOLDS_DAYS=[10, 4, 0])
    def test_los_umbrales_se_configuran(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Lejano", dias=9)
        generar_alertas(self.hoy)
        self.assertEqual(Notificacion.objects.get(entregable=e, usuario=self.j1).umbral, 10)

    def test_una_notificacion_por_umbral_a_lo_largo_de_los_dias(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Seguimiento", dias=6)
        for avance in range(0, 8):
            generar_alertas(self.hoy + datetime.timedelta(days=avance))
        umbrales = sorted(Notificacion.objects.filter(entregable=e, usuario=self.j1).values_list("umbral", flat=True))
        self.assertEqual(umbrales, [0, 2, 5])  # ni más ni menos, aunque el proceso corra todos los días


class ProgramadorTests(Base):
    def test_define_las_dos_tareas(self):
        p = programador.crear_programador()
        self.assertEqual({job.id for job in p.get_jobs()}, {"alertas", "lecciones"})
        self.assertEqual({job.name for job in p.get_jobs()}, {"Alertas de vencimiento", "Indexación de lecciones aprendidas"})
        self.assertEqual(str(p.timezone), "America/Lima")

    def test_la_tarea_de_alertas_genera_las_notificaciones(self):
        self.nuevo(self.c1, self.j1, self.s1, "Hoy", dias=0)
        self.assertEqual(programador.tarea_alertas(), 2)
        self.assertEqual(programador.tarea_alertas(), 0)  # idempotente

    def test_la_tarea_de_lecciones_no_llama_a_ollama_si_no_hay_nada_que_indexar(self):
        with mock.patch("apps.conocimiento.ollama._post", side_effect=Exception("no debería llamarse")) as llamada:
            self.assertEqual(programador.tarea_lecciones(), (0, 0))
        llamada.assert_not_called()

    def test_cierra_las_conexiones_viejas_antes_y_despues(self):
        with mock.patch("apps.alertas.programador.close_old_connections") as cerrar:
            programador._con_conexion_limpia(lambda: "ok")()
        self.assertEqual(cerrar.call_count, 2)

    def test_el_comando_existe(self):
        from django.core.management import get_commands

        self.assertIn("programador", get_commands())
