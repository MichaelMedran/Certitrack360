"""Pruebas de los reportes de avance (SDD del Sprint 3, RF-50: HU-31; caso 40 de la §13)."""
import datetime
import os
from io import BytesIO
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from apps.alertas import programador
from apps.alertas.models import Notificacion
from apps.cuentas.models import Usuario
from apps.entregables.models import Entregable, Observacion
from apps.entregables.tests import Base
from apps.reportes import servicios
from apps.reportes.models import ConfiguracionReporte, ReporteAvance

E = Entregable.Estado
P = ConfiguracionReporte.Periodicidad
ZONA = timezone.get_current_timezone()


def lima(anio, mes, dia, hora=8, minuto=0):
    return datetime.datetime(anio, mes, dia, hora, minuto, tzinfo=ZONA)


def texto_pdf(reporte):
    with reporte.archivo.open("rb") as f:
        return "\n".join(p.extract_text() for p in PdfReader(BytesIO(f.read())).pages)


class CifrasTests(Base):
    def test_cifras_por_estado_vencidos_por_vencer_y_observaciones(self):
        self.nuevo(self.c1, self.j1, self.s1, "Vencido", dias=-3)
        self.nuevo(self.c1, self.j1, self.s1, "Por vencer", dias=2)
        self.nuevo(self.c1, self.j1, self.s1, "Hecho vencido", estado=E.HECHO, dias=-5)
        Observacion.objects.create(entregable=self.e1, autor=self.s1, tipo_error="FORMATO", descripcion="x")
        Observacion.objects.create(entregable=self.e1, autor=self.s1, tipo_error="FORMATO", descripcion="y",
                                   estado=Observacion.Estado.EN_CORRECCION)
        datos = servicios.calcular_datos()
        t = datos["totales"]
        self.assertEqual(t["total"], 5)
        self.assertEqual(t["activos"], 4)  # el entregado no cuenta como activo
        self.assertEqual(t["vencidos"], 1)  # ni el entregado vencido
        self.assertEqual(t["por_vencer"], 1)
        self.assertEqual(t["observaciones_pendientes"], 1)  # la «en corrección» ya tiene acción correctiva
        self.assertEqual(t["por_estado"][E.HECHO], 1)
        self.assertEqual(len(datos["clientes"]), 1)
        contratos = {c["nombre"]: c for c in datos["clientes"][0]["contratos"]}
        self.assertEqual(contratos["C1"]["total"], 4)
        self.assertEqual(contratos["C2"]["total"], 1)
        self.assertEqual(contratos["C1"]["observaciones_pendientes"], 1)
        self.assertIn("datos_al", datos)

    def test_sin_entregables_no_falla_y_lo_dice_el_pdf(self):
        Entregable.objects.all().delete()
        reporte = servicios.generar(ReporteAvance.Origen.MANUAL, usuario=self.gerente)
        self.assertEqual(reporte.datos["totales"]["total"], 0)
        self.assertIn("No hay entregables registrados", texto_pdf(reporte))


class GeneracionAPedidoTests(Base):
    def test_el_gerente_genera_guarda_pdf_y_avisa_a_los_gerentes_activos(self):
        otro = Usuario.objects.create_user("ger2", password="x", rol="GERENTE")
        Usuario.objects.create_user("ger3", password="x", rol="GERENTE", is_active=False)
        self.client.force_login(self.gerente)
        r = self.client.post(reverse("reporte_generar"))
        reporte = ReporteAvance.objects.get()
        self.assertRedirects(r, reverse("reporte_detalle", args=[reporte.pk]))
        self.assertEqual(reporte.origen, "MANUAL")
        self.assertEqual(reporte.generado_por, self.gerente)
        self.assertTrue(reporte.archivo.name.startswith("reportes/"))
        avisos = Notificacion.objects.filter(tipo=Notificacion.Tipo.REPORTE)
        self.assertEqual(set(avisos.values_list("usuario__username", flat=True)), {"ger", otro.username})
        self.assertEqual(avisos.first().enlace, reverse("reporte_detalle", args=[reporte.pk]))

    def test_el_pdf_se_abre_y_trae_las_cifras(self):
        reporte = servicios.generar(ReporteAvance.Origen.MANUAL, usuario=self.gerente)
        with reporte.archivo.open("rb") as f:
            lector = PdfReader(BytesIO(f.read()))
        self.assertGreaterEqual(len(lector.pages), 1)
        texto = texto_pdf(reporte)
        for esperado in ("Reporte de avance de entregables", "Datos al", "Totales del área", "Cliente Demo", "C1", "C2",
                         "A pedido"):
            self.assertIn(esperado, texto)

    def test_descarga_del_pdf_guardado_y_vista_en_pantalla(self):
        reporte = servicios.generar(ReporteAvance.Origen.MANUAL, usuario=self.gerente)
        self.client.force_login(self.gerente)
        r = self.client.get(reverse("reporte_pdf", args=[reporte.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertEqual(len(PdfReader(BytesIO(b"".join(r.streaming_content))).pages), 1)
        r = self.client.get(reverse("reporte_detalle", args=[reporte.pk]))
        self.assertContains(r, "Datos al")
        self.assertContains(r, "Cliente Demo")
        self.assertContains(r, "data-imprimir")

    def test_cada_reporte_se_guarda_sin_sobrescribir_al_anterior(self):
        a = servicios.generar(ReporteAvance.Origen.MANUAL, usuario=self.gerente)
        b = servicios.generar(ReporteAvance.Origen.MANUAL, usuario=self.gerente)
        self.assertNotEqual(a.archivo.name, b.archivo.name)
        self.assertEqual(ReporteAvance.objects.count(), 2)

    def test_pdf_perdido_responde_404(self):
        reporte = servicios.generar(ReporteAvance.Origen.MANUAL, usuario=self.gerente)
        reporte.archivo.storage.delete(reporte.archivo.name)
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(reverse("reporte_pdf", args=[reporte.pk])).status_code, 404)

    def test_borrar_el_reporte_borra_su_pdf(self):
        reporte = servicios.generar(ReporteAvance.Origen.MANUAL, usuario=self.gerente)
        almacenamiento, nombre = reporte.archivo.storage, reporte.archivo.name
        with self.captureOnCommitCallbacks(execute=True):
            reporte.delete()
        self.assertFalse(almacenamiento.exists(nombre))

    def test_si_falla_el_guardado_no_queda_reporte_ni_pdf_huerfano(self):
        carpeta = ReporteAvance._meta.get_field("archivo").storage.path("reportes")
        antes = set(os.listdir(carpeta)) if os.path.isdir(carpeta) else set()
        with mock.patch.object(servicios, "_avisar_a_gerentes", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                servicios.generar(ReporteAvance.Origen.MANUAL, usuario=self.gerente)
        self.assertEqual(ReporteAvance.objects.count(), 0)
        self.assertEqual(set(os.listdir(carpeta)) if os.path.isdir(carpeta) else set(), antes)


class PermisosTests(Base):
    def setUp(self):
        self.reporte = servicios.generar(ReporteAvance.Origen.MANUAL, usuario=self.gerente)

    def urls(self):
        return [reverse("reportes"), reverse("reporte_detalle", args=[self.reporte.pk]),
                reverse("reporte_pdf", args=[self.reporte.pk])]

    def test_senior_y_junior_reciben_403_en_todo(self):
        for usuario in (self.s1, self.j1):
            self.client.force_login(usuario)
            for url in self.urls():
                self.assertEqual(self.client.get(url).status_code, 403, (usuario.rol, url))
            self.assertEqual(self.client.post(reverse("reporte_generar")).status_code, 403)
            self.assertEqual(self.client.post(reverse("reportes"), {"periodicidad": "DIARIA"}).status_code, 403)
        self.assertEqual(ReporteAvance.objects.count(), 1)
        self.assertEqual(ConfiguracionReporte.cargar().periodicidad, P.SEMANAL)

    def test_sin_sesion_va_al_ingreso(self):
        for url in self.urls():
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302)
            self.assertIn("next=", r["Location"])

    def test_gerente_y_admin_acceden(self):
        for usuario in (self.gerente, self.admin):
            self.client.force_login(usuario)
            for url in self.urls():
                self.assertEqual(self.client.get(url).status_code, 200, (usuario.rol, url))

    def test_generar_exige_post(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(reverse("reporte_generar")).status_code, 405)

    def test_la_lista_muestra_los_reportes_y_la_pestana(self):
        self.client.force_login(self.gerente)
        r = self.client.get(reverse("reportes"))
        self.assertContains(r, "Generar reporte")
        self.assertContains(r, reverse("reporte_detalle", args=[self.reporte.pk]))
        self.assertContains(r, "A pedido")


class ConfiguracionTests(Base):
    def test_se_crea_semanal_con_ultimo_automatico(self):
        config = ConfiguracionReporte.cargar()
        self.assertEqual((config.periodicidad, config.dia_semana, config.hora), (P.SEMANAL, 0, datetime.time(8, 0)))
        self.assertIsNotNone(config.ultimo_automatico)
        self.assertEqual(ConfiguracionReporte.cargar().pk, config.pk)

    def test_el_gerente_edita_la_periodicidad(self):
        self.client.force_login(self.gerente)
        r = self.client.post(reverse("reportes"), {"periodicidad": "MENSUAL", "dia_semana": 2, "dia_mes": 15, "hora": "09:30"})
        self.assertRedirects(r, reverse("reportes"))
        config = ConfiguracionReporte.cargar()
        self.assertEqual((config.periodicidad, config.dia_semana, config.dia_mes), (P.MENSUAL, 2, 15))
        self.assertEqual(config.hora, datetime.time(9, 30))

    def test_dia_del_mes_fuera_de_1_a_28_se_rechaza(self):
        self.client.force_login(self.gerente)
        for dia in (0, 29, 31):
            r = self.client.post(reverse("reportes"), {"periodicidad": "MENSUAL", "dia_semana": 0, "dia_mes": dia, "hora": "08:00"})
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, "Elija un día del 1 al 28")
        self.assertEqual(ConfiguracionReporte.cargar().periodicidad, P.SEMANAL)


class MomentoProgramadoTests(TestCase):
    def config(self, **kw):
        return ConfiguracionReporte(hora=datetime.time(8, 0), **kw)

    def test_diaria(self):
        c = self.config(periodicidad=P.DIARIA)
        self.assertEqual(servicios.momento_programado(c, lima(2026, 11, 11, 9)), lima(2026, 11, 11, 8))
        self.assertEqual(servicios.momento_programado(c, lima(2026, 11, 11, 7)), lima(2026, 11, 10, 8))

    def test_semanal(self):
        c = self.config(periodicidad=P.SEMANAL, dia_semana=0)  # lunes; el 9/11/2026 es lunes
        self.assertEqual(servicios.momento_programado(c, lima(2026, 11, 11, 12)), lima(2026, 11, 9, 8))
        self.assertEqual(servicios.momento_programado(c, lima(2026, 11, 9, 7)), lima(2026, 11, 2, 8))
        self.assertEqual(servicios.momento_programado(c, lima(2026, 11, 9, 8, 1)), lima(2026, 11, 9, 8))

    def test_mensual(self):
        c = self.config(periodicidad=P.MENSUAL, dia_mes=5)
        self.assertEqual(servicios.momento_programado(c, lima(2026, 11, 11)), lima(2026, 11, 5, 8))
        self.assertEqual(servicios.momento_programado(c, lima(2026, 11, 3)), lima(2026, 10, 5, 8))
        self.assertEqual(servicios.momento_programado(c, lima(2027, 1, 2)), lima(2026, 12, 5, 8))

    def test_desactivada(self):
        self.assertIsNone(servicios.momento_programado(self.config(periodicidad=P.DESACTIVADA), lima(2026, 11, 11)))


class ReporteAutomaticoTests(Base):
    """Caso 40: se genera una vez por periodo, avisa al gerente y no repite aunque la tarea corra varias veces."""

    def configurar(self, ultimo, **kw):
        config = ConfiguracionReporte.cargar()
        for campo, valor in kw.items():
            setattr(config, campo, valor)
        config.ultimo_automatico = ultimo
        config.save()
        return config

    def test_semanal_genera_una_sola_vez_por_periodo(self):
        self.configurar(lima(2026, 11, 2, 8, 5), periodicidad=P.SEMANAL, dia_semana=0)
        self.assertIsNone(servicios.generar_si_corresponde(lima(2026, 11, 8, 12)))  # aún no llega el lunes 9
        self.assertIsNone(servicios.generar_si_corresponde(lima(2026, 11, 9, 7, 30)))
        reporte = servicios.generar_si_corresponde(lima(2026, 11, 9, 8, 10))
        self.assertIsNotNone(reporte)
        self.assertEqual(reporte.origen, "AUTOMATICO")
        self.assertIsNone(reporte.generado_por)
        for hora in (9, 12, 23):  # la tarea corre cada hora, pero ya se generó el de este periodo
            self.assertIsNone(servicios.generar_si_corresponde(lima(2026, 11, 9, hora)))
        self.assertIsNone(servicios.generar_si_corresponde(lima(2026, 11, 12)))
        self.assertEqual(ReporteAvance.objects.count(), 1)
        siguiente = servicios.generar_si_corresponde(lima(2026, 11, 16, 8, 1))
        self.assertIsNotNone(siguiente)
        self.assertEqual(ReporteAvance.objects.count(), 2)

    def test_avisa_al_gerente_y_el_pdf_se_abre(self):
        self.configurar(lima(2026, 11, 8), periodicidad=P.DIARIA)
        reporte = servicios.generar_si_corresponde(lima(2026, 11, 9, 8, 30))
        aviso = Notificacion.objects.get(tipo=Notificacion.Tipo.REPORTE)
        self.assertEqual(aviso.usuario, self.gerente)
        self.assertEqual(aviso.enlace, reverse("reporte_detalle", args=[reporte.pk]))
        self.assertFalse(Notificacion.objects.filter(usuario__in=[self.s1, self.j1], tipo=Notificacion.Tipo.REPORTE).exists())
        self.assertIn("Automático", texto_pdf(reporte))
        self.assertEqual(reporte.datos_al, lima(2026, 11, 9, 8, 30))

    def test_desactivada_no_genera(self):
        self.configurar(lima(2026, 1, 1), periodicidad=P.DESACTIVADA)
        self.assertIsNone(servicios.generar_si_corresponde(lima(2026, 11, 9, 9)))
        self.assertEqual(ReporteAvance.objects.count(), 0)

    def test_un_reporte_a_pedido_no_cuenta_como_el_del_periodo(self):
        self.configurar(lima(2026, 11, 8), periodicidad=P.DIARIA)
        servicios.generar(ReporteAvance.Origen.MANUAL, usuario=self.gerente, ahora=lima(2026, 11, 9, 7))
        self.assertIsNotNone(servicios.generar_si_corresponde(lima(2026, 11, 9, 8, 30)))
        self.assertEqual(ReporteAvance.objects.count(), 2)

    def test_la_primera_vez_no_genera_al_arrancar(self):
        ConfiguracionReporte.objects.all().delete()
        ahora = timezone.now()
        self.assertIsNone(servicios.generar_si_corresponde(ahora))
        self.assertEqual(ReporteAvance.objects.count(), 0)

    def test_si_otra_ejecucion_ya_reclamo_el_periodo_no_se_duplica(self):
        config = self.configurar(lima(2026, 11, 8), periodicidad=P.DIARIA)
        ahora = lima(2026, 11, 9, 8, 30)

        def competidora(config_, ahora_):  # simula a la otra ejecución: reclama el periodo después de la comprobación
            ConfiguracionReporte.objects.filter(pk=config.pk).update(ultimo_automatico=ahora)
            return True

        with mock.patch.object(servicios, "corresponde_generar", side_effect=competidora):
            self.assertIsNone(servicios.generar_si_corresponde(ahora))
        self.assertEqual(ReporteAvance.objects.count(), 0)

    def test_si_la_generacion_falla_se_reintenta_en_la_siguiente_hora(self):
        self.configurar(lima(2026, 11, 8), periodicidad=P.DIARIA)
        with mock.patch.object(servicios, "_avisar_a_gerentes", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                servicios.generar_si_corresponde(lima(2026, 11, 9, 8, 30))
        self.assertEqual(ConfiguracionReporte.cargar().ultimo_automatico, lima(2026, 11, 8))
        self.assertIsNotNone(servicios.generar_si_corresponde(lima(2026, 11, 9, 9, 30)))
        self.assertEqual(ReporteAvance.objects.count(), 1)


class TareaProgramadaTests(Base):
    def test_tarea_reporte_genera_y_un_fallo_no_frena_las_alertas(self):
        config = ConfiguracionReporte.cargar()
        config.periodicidad = P.DIARIA
        config.ultimo_automatico = timezone.now() - datetime.timedelta(days=3)
        config.hora = datetime.time(0, 0)
        config.save()
        self.assertIsNotNone(programador.tarea_reporte())
        self.assertIsNone(programador.tarea_reporte())  # el mismo día no repite
        self.assertEqual(ReporteAvance.objects.filter(origen="AUTOMATICO").count(), 1)

    def test_error_al_generar_se_registra_y_no_propaga(self):
        with mock.patch("apps.reportes.servicios.generar_si_corresponde", side_effect=RuntimeError("falla")):
            with self.assertLogs("apps.alertas.programador", level="ERROR"):
                self.assertIsNone(programador.tarea_reporte())

    def test_tarea_alertas_invoca_al_reporte(self):
        with mock.patch.object(programador, "tarea_reporte") as tarea:
            programador.tarea_alertas()
        tarea.assert_called_once()
