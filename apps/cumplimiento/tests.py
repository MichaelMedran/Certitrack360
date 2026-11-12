"""Penalidades incurridas por entregable y vigencia de los certificados del cliente."""
import datetime
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from django.urls import reverse

from apps.alertas.models import Notificacion
from apps.alertas.programador import tarea_alertas
from apps.clientes.models import Cliente, PlantillaTDR
from apps.cumplimiento import servicios
from apps.cumplimiento.models import DocumentoVigencia, Penalidad
from apps.entregables import servicios as entregables_srv
from apps.entregables.models import Entregable
from apps.entregables.tests import Base

E = Entregable.Estado


class DosClientes(Base):
    """El contrato C2 (senior s2, junior j2) pasa a ser de otro cliente, para probar la separación por cliente."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.c2.cliente = Cliente.objects.create(nombre="Cliente Otro", sector="TELECOM")
        cls.c2.save()
        cls.e2 = Entregable.objects.select_related("contrato__cliente").get(pk=cls.e2.pk)


class PenalidadesTests(DosClientes):
    def test_el_senior_registra_y_queda_en_el_historial(self):
        p = servicios.registrar_penalidad(self.s1, self.e1, "  Entrega   con 3 días de retraso ", "1.250,50", self.hoy.isoformat())
        self.assertEqual((p.motivo, p.monto, p.fecha), ("Entrega con 3 días de retraso", Decimal("1250.50"), self.hoy))
        self.assertTrue(self.e1.historial.filter(detalle__startswith="Registró una penalidad").exists())

    def test_el_monto_es_opcional_y_acepta_los_formatos_habituales(self):
        casos = {"": None, "S/ 300": Decimal("300.00"), "1250.5": Decimal("1250.50"), "0,75": Decimal("0.75")}
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(servicios.registrar_penalidad(self.s1, self.e1, "Retraso", texto).monto, esperado)

    def test_rechaza_datos_invalidos(self):
        manana = (self.hoy + datetime.timedelta(days=1)).isoformat()
        for motivo, monto, fecha in (("", "10", None), ("Retraso", "abc", None), ("Retraso", "-5", None),
                                     ("Retraso", "10", manana), ("Retraso", "10", "31/02/2026"), ("Retraso", "NaN", None)):
            with self.subTest(motivo=motivo, monto=monto, fecha=fecha), self.assertRaises(ValidationError):
                servicios.registrar_penalidad(self.s1, self.e1, motivo, monto, fecha)
        self.assertEqual(Penalidad.objects.count(), 0)

    def test_solo_el_senior_del_entregable_el_gerente_y_el_admin_registran(self):
        for usuario in (self.j1, self.s2):
            with self.subTest(usuario=usuario.username), self.assertRaises(PermissionDenied):
                servicios.registrar_penalidad(usuario, self.e1, "Retraso")
        for usuario in (self.s1, self.gerente, self.admin):
            servicios.registrar_penalidad(usuario, self.e1, "Retraso")
        self.assertEqual(self.e1.penalidades.count(), 3)

    def test_dias_de_atraso_de_un_entregable_abierto_y_de_uno_al_dia(self):
        self.assertEqual(servicios.dias_atraso(self.e1), 0)
        Entregable.objects.filter(pk=self.e1.pk).update(plazo=self.hoy - datetime.timedelta(days=4))
        self.e1.refresh_from_db()
        self.assertEqual(servicios.dias_atraso(self.e1), 4)

    def test_la_seccion_del_detalle_segun_el_rol(self):
        self.client.force_login(self.j1)
        html = self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).content.decode()
        self.assertNotIn('id="penalidades"', html)  # sin atraso ni penalidades, al junior no se le muestra

        servicios.registrar_penalidad(self.s1, self.e1, "Observación reiterada", "200")
        html = self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).content.decode()
        self.assertIn("Observación reiterada", html)
        self.assertIn("200,00", html)
        self.assertNotIn("Registrar una penalidad", html)

        self.client.force_login(self.s1)
        html = self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).content.decode()
        self.assertIn("Registrar una penalidad", html)

    def test_el_atraso_se_advierte_en_el_detalle(self):
        Entregable.objects.filter(pk=self.e1.pk).update(plazo=self.hoy - datetime.timedelta(days=2))
        self.client.force_login(self.j1)
        html = self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).content.decode()
        self.assertIn("2 días de atraso", html)

    def test_registrar_y_eliminar_desde_la_pantalla(self):
        self.client.force_login(self.s1)
        r = self.client.post(reverse("entregable_penalidad", args=[self.e1.pk]), {"motivo": "Retraso", "monto": "150"})
        self.assertRedirects(r, reverse("entregable_detalle", args=[self.e1.pk]) + "#penalidades", fetch_redirect_response=False)
        penalidad = Penalidad.objects.get()
        r = self.client.post(reverse("entregable_penalidad", args=[self.e1.pk]), {"motivo": "", "monto": "1"}, follow=True)
        self.assertContains(r, "Indique el motivo")
        self.client.post(reverse("penalidad_eliminar", args=[penalidad.pk]))
        self.assertEqual(Penalidad.objects.count(), 0)

    def test_nadie_toca_penalidades_de_entregables_que_no_ve_ni_gestiona(self):
        penalidad = servicios.registrar_penalidad(self.s1, self.e1, "Retraso")
        self.client.force_login(self.j2)  # no ve e1
        self.assertEqual(self.client.post(reverse("entregable_penalidad", args=[self.e1.pk]), {"motivo": "x"}).status_code, 404)
        self.assertEqual(self.client.post(reverse("penalidad_eliminar", args=[penalidad.pk])).status_code, 404)
        self.client.force_login(self.j1)  # lo ve, pero no gestiona
        self.assertEqual(self.client.post(reverse("entregable_penalidad", args=[self.e1.pk]), {"motivo": "x"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("penalidad_eliminar", args=[penalidad.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("entregable_penalidad", args=[self.e1.pk])).status_code, 405)
        self.assertEqual(Penalidad.objects.count(), 1)

    def test_la_pestana_suma_solo_lo_visible(self):
        servicios.registrar_penalidad(self.s1, self.e1, "Retraso en e1", "100")
        servicios.registrar_penalidad(self.s1, self.e1, "Sin monto")
        servicios.registrar_penalidad(self.s2, self.e2, "Retraso en e2", "40,50")
        self.assertEqual(servicios.listado_penalidades(self.gerente)["total"], Decimal("140.50"))
        self.assertEqual(servicios.listado_penalidades(self.j1)["total"], Decimal("100.00"))
        self.assertEqual(servicios.listado_penalidades(self.j2)["total"], Decimal("40.50"))
        self.assertEqual(
            servicios.listado_penalidades(self.gerente, self.e2.contrato.cliente_id)["total"], Decimal("40.50"))

        self.client.force_login(self.j1)
        html = self.client.get(reverse("penalidades")).content.decode()
        self.assertIn("Retraso en e1", html)
        self.assertNotIn("Retraso en e2", html)
        self.assertIn('aria-current="true">Penalidades</a>', html)
        self.assertIn("S/ 100,00", html)
        self.assertEqual(self.client.get(reverse("penalidades"), {"cliente": "abc"}).status_code, 200)

    def test_sin_sesion_va_al_ingreso(self):
        for nombre in ("penalidades", "vigencias"):
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 302)


class VigenciasTests(DosClientes):
    def doc(self, dias, cliente=None, nombre="Certificado ISO 9001"):
        return DocumentoVigencia.objects.create(
            cliente=cliente or self.c1.cliente, nombre=nombre, vence=self.hoy + datetime.timedelta(days=dias),
            creado_por=self.gerente)

    def test_estado_segun_la_fecha(self):
        casos = {-1: servicios.VENCIDO, 0: servicios.POR_VENCER, 30: servicios.POR_VENCER, 31: servicios.VIGENTE}
        for dias, estado in casos.items():
            with self.subTest(dias=dias):
                self.assertEqual(servicios.estado_vigencia(self.doc(dias)), estado)

    def test_quien_puede_registrar(self):
        cliente1, cliente2 = self.c1.cliente, self.c2.cliente
        servicios.registrar_documento(self.gerente, cliente2, "Póliza", self.hoy.isoformat())
        servicios.registrar_documento(self.s1, cliente1, " ISO   27001 ", (self.hoy + datetime.timedelta(days=90)).isoformat())
        self.assertTrue(DocumentoVigencia.objects.filter(nombre="ISO 27001").exists())
        for usuario, cliente in ((self.j1, cliente1), (self.s1, cliente2)):
            with self.subTest(usuario=usuario.username), self.assertRaises(PermissionDenied):
                servicios.registrar_documento(usuario, cliente, "ISO", self.hoy.isoformat())
        for nombre, vence in (("", self.hoy.isoformat()), ("ISO", "no es fecha"), ("ISO", "")):
            with self.subTest(nombre=nombre, vence=vence), self.assertRaises(ValidationError):
                servicios.registrar_documento(self.gerente, cliente1, nombre, vence)

    def test_avisa_una_vez_antes_y_una_vez_al_vencer(self):
        doc = self.doc(10)
        self.doc(200, nombre="Licencia lejana")
        self.assertEqual(servicios.generar_alertas_vigencia(), 2)  # senior del contrato y gerente
        self.assertEqual(servicios.generar_alertas_vigencia(), 0)
        avisos = Notificacion.objects.filter(tipo=Notificacion.Tipo.VIGENCIA)
        self.assertEqual({a.usuario for a in avisos}, {self.s1, self.gerente})
        self.assertIn("vence en 10 días", avisos[0].mensaje)
        self.assertEqual(avisos[0].destino, reverse("vigencias"))

        despues = self.hoy + datetime.timedelta(days=11)
        self.assertEqual(servicios.generar_alertas_vigencia(hoy=despues), 2)
        self.assertEqual(servicios.generar_alertas_vigencia(hoy=despues), 0)
        self.assertTrue(Notificacion.objects.filter(mensaje__contains="venció el").exists())
        doc.refresh_from_db()
        self.assertIsNotNone(doc.aviso_previo_en)
        self.assertIsNotNone(doc.aviso_vencido_en)

    def test_renovar_reinicia_los_avisos_y_retirar_los_detiene(self):
        doc = self.doc(-3)
        servicios.generar_alertas_vigencia()
        servicios.renovar_documento(self.gerente, doc, (self.hoy + datetime.timedelta(days=5)).isoformat())
        doc.refresh_from_db()
        self.assertIsNone(doc.aviso_vencido_en)
        self.assertEqual(servicios.generar_alertas_vigencia(), 2)
        otro = self.doc(-1, nombre="Póliza")
        servicios.retirar_documento(self.gerente, otro)
        self.assertEqual(servicios.generar_alertas_vigencia(), 0)
        with self.assertRaises(PermissionDenied):
            servicios.renovar_documento(self.j1, doc, self.hoy.isoformat())

    def test_el_programador_incluye_los_avisos_de_vigencia(self):
        self.doc(-1)
        tarea_alertas()
        self.assertEqual(Notificacion.objects.filter(tipo=Notificacion.Tipo.VIGENCIA).count(), 2)

    @override_settings(VIGENCIA_DIAS_AVISO=5)
    def test_los_dias_de_aviso_son_configurables(self):
        self.doc(10)
        self.assertEqual(servicios.generar_alertas_vigencia(), 0)

    def test_enviar_a_revision_con_un_documento_vencido_pide_confirmacion(self):
        self.assertIsNone(servicios.condicion_vigencias(self.e1, E.VERIFICACION_SENIOR, self.j1, {}))
        self.doc(-2)
        self.doc(-2, cliente=self.c2.cliente, nombre="De otro cliente")
        aviso = servicios.condicion_vigencias(self.e1, E.VERIFICACION_SENIOR, self.j1, {})
        self.assertEqual(aviso.clave, servicios.CLAVE_VIGENCIA)
        self.assertIn("Certificado ISO 9001", aviso.mensaje)
        self.assertNotIn("De otro cliente", aviso.mensaje)
        self.assertIsNone(servicios.condicion_vigencias(self.e1, E.EN_PROCESO, self.j1, {}))

        entregables_srv.mover(self.e1, E.EN_PROCESO, self.j1)
        with self.assertRaises(ValidationError) as ctx:
            entregables_srv.mover(self.e1, E.VERIFICACION_SENIOR, self.j1)
        self.assertIn("documentos vencidos", " ".join(ctx.exception.messages))

    def test_la_seccion_del_detalle_muestra_el_estado(self):
        self.client.force_login(self.j1)
        html = self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).content.decode()
        self.assertNotIn('id="vigencias"', html)
        self.doc(-2)
        self.doc(12, nombre="Póliza de seguro")
        html = self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).content.decode()
        self.assertIn("tiene documentos vencidos", html)
        self.assertIn("Por vencer · 12 días", html)
        self.assertNotIn("Registrar o renovar documentos", html)
        self.client.force_login(self.s1)
        html = self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).content.decode()
        self.assertIn("Registrar o renovar documentos", html)

    def test_la_pantalla_respeta_la_visibilidad_y_los_permisos(self):
        propio = self.doc(40)
        ajeno = self.doc(40, cliente=self.c2.cliente, nombre="Certificado ajeno")
        self.client.force_login(self.s1)
        html = self.client.get(reverse("vigencias")).content.decode()
        self.assertIn("Certificado ISO 9001", html)
        self.assertNotIn("Certificado ajeno", html)
        self.assertEqual(self.client.post(reverse("vigencia_actualizar", args=[ajeno.pk]), {"accion": "retirar"}).status_code, 404)

        nueva = (self.hoy + datetime.timedelta(days=400)).isoformat()
        self.client.post(reverse("vigencia_actualizar", args=[propio.pk]), {"vence": nueva})
        propio.refresh_from_db()
        self.assertEqual(propio.vence.isoformat(), nueva)
        self.client.post(reverse("vigencias"), {"cliente": self.c1.cliente_id, "nombre": "Licencia", "vence": nueva})
        self.assertTrue(DocumentoVigencia.objects.filter(nombre="Licencia", creado_por=self.s1).exists())
        self.assertEqual(
            self.client.post(reverse("vigencias"), {"cliente": self.c2.cliente_id, "nombre": "X", "vence": nueva}).status_code, 403)

        self.client.force_login(self.j1)
        html = self.client.get(reverse("vigencias")).content.decode()
        self.assertIn("Certificado ISO 9001", html)
        self.assertNotIn("Registrar un documento", html)
        self.assertEqual(self.client.post(reverse("vigencia_actualizar", args=[propio.pk]), {"accion": "retirar"}).status_code, 403)

        self.client.force_login(self.gerente)
        html = self.client.get(reverse("vigencias")).content.decode()
        self.assertIn('aria-current="page">Certificados</a>', html)
        self.assertIn("Certificado ajeno", html)


class NumeracionYCargaTests(DosClientes):
    def test_el_numero_de_reporte_es_correlativo_por_contrato_y_tipo(self):
        segundo = self.nuevo(self.c1, self.j1, self.s1, "E1 bis")
        otro_tipo = Entregable.objects.create(
            contrato=self.c1, plantilla=PlantillaTDR.objects.create(nombre="Acta"), titulo="Acta 1", plazo=self.hoy,
            junior_asignado=self.j1, senior_revisor=self.s1, creado_por=self.s1)
        self.assertEqual([self.e1.numero_correlativo, segundo.numero_correlativo], [1, 2])
        self.assertEqual(self.e2.numero_correlativo, 1)  # otro contrato: su propia serie
        self.assertEqual(otro_tipo.numero_correlativo, 1)  # otro tipo de entregable: su propia serie
        self.assertIsNone(Entregable().numero_correlativo)

        from apps.exportacion.servicios import datos_consolidados

        self.assertIn(("numero_reporte", "N.º de reporte", "2"), datos_consolidados(segundo))
        self.client.force_login(self.s1)
        self.assertContains(self.client.get(reverse("entregable_detalle", args=[segundo.pk])), "P n.º 2")

    def test_el_selector_de_junior_muestra_la_carga(self):
        self.nuevo(self.c1, self.j1, self.s1, "Otro activo")
        self.nuevo(self.c1, self.j1, self.s1, "Ya entregado", estado=E.HECHO)
        self.client.force_login(self.s1)
        html = self.client.get(reverse("entregable_nuevo"), {"plantilla": self.plantilla.pk}).content.decode()
        self.assertIn("j1 · 2 activos</option>", html)
        self.assertIn("j2 · 1 activo</option>", html)
