"""SDD del Sprint 3, hito S3-H7 (verificación del número de factura, RF-46, HU-30) y caso 36 de la §13.

Una factura inexistente, anulada o de otro cliente impide aprobar; la justificación del senior lo permite; un junior no
justifica; cada verificación queda en el historial. La base de facturación es simulada y de solo lectura.
"""
import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from django.urls import reverse

from apps.alertas.models import Notificacion
from apps.clientes.models import Cliente
from apps.entregables import servicios
from apps.entregables.models import Entregable
from apps.entregables.testing import aprobar
from apps.entregables.tests import Base
from apps.facturacion import verificacion
from apps.facturacion.conector import ConectorSimulado, ErrorConexion, obtener_conector
from apps.facturacion.models import FacturaSimulada, VerificacionFactura

E = Entregable.Estado
R = VerificacionFactura.Resultado
F = FacturaSimulada.Estado


class ConectorCaido:
    def consultar(self, numero):
        raise ErrorConexion("sin red")


class FacturaBase(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.otro_cliente = Cliente.objects.create(nombre="Telecom Sur", sector="TELECOM")
        cls.rev = cls.nuevo(cls.c1, cls.j1, cls.s1, "En revisión", E.VERIFICACION_SENIOR)
        fecha = datetime.date(2026, 10, 1)

        def factura(numero, cliente, contrato, estado=F.EMITIDA):
            return FacturaSimulada.objects.create(numero=numero, cliente_nombre=cliente, contrato_numero=contrato,
                                                  estado=estado, fecha_emision=fecha, monto="1500.00")

        factura("F001-00119", cls.cliente.nombre, "C1")
        factura("F001-00120", cls.cliente.nombre, "C1", F.PAGADA)
        factura("F001-00123", cls.otro_cliente.nombre, "C1")
        factura("F001-00124", cls.cliente.nombre, "C2")
        factura("F001-00125", cls.cliente.nombre, "C1", F.ANULADA)

    def aprobar_falla(self, usuario=None, texto="la factura"):
        with self.assertRaisesMessage(ValidationError, texto):
            servicios.mover(self.rev, E.LISTO_PARA_ENTREGA, usuario or self.s1)
        self.assertEqual(Entregable.objects.get(pk=self.rev.pk).estado, E.VERIFICACION_SENIOR)


class ConectorTests(FacturaBase):
    def test_el_conector_configurado_es_el_simulado(self):
        self.assertIsInstance(obtener_conector(), ConectorSimulado)

    def test_consulta_en_solo_lectura(self):
        self.assertEqual(ConectorSimulado().consultar("f001-00119")["contrato"], "C1")
        self.assertIsNone(ConectorSimulado().consultar("NO-EXISTE"))
        self.assertEqual(FacturaSimulada.objects.count(), 5)
        self.assertFalse(hasattr(ConectorSimulado, "guardar") or hasattr(ConectorSimulado, "crear"))

    @override_settings(FACTURACION_CONECTOR="apps.facturacion.tests.ConectorCaido")
    def test_un_conector_configurable_y_un_fallo_queda_como_sin_conexion(self):
        v = verificacion.verificar(self.rev, self.j1, "F001-00119")
        self.assertEqual(v.resultado, R.SIN_CONEXION)
        self.aprobar_falla()


class VerificacionTests(FacturaBase):
    """Resultado de cada verificación y su registro (HU-30 criterios 1, 2 y 4)."""

    def resultado(self, numero):
        return verificacion.verificar(self.rev, self.j1, numero)

    def test_cada_resultado(self):
        self.assertEqual(self.resultado("F001-00119").resultado, R.CORRECTA)
        self.assertEqual(self.resultado("F001-00120").resultado, R.CORRECTA)  # pagada también sirve
        self.assertEqual(self.resultado("F999-00001").resultado, R.NO_EXISTE)
        self.assertEqual(self.resultado("F001-00123").resultado, R.OTRO_CLIENTE)
        self.assertEqual(self.resultado("F001-00124").resultado, R.OTRO_CONTRATO)
        self.assertEqual(self.resultado("F001-00125").resultado, R.ANULADA)

    def test_el_motivo_es_exacto(self):
        v = self.resultado("F001-00123")
        self.assertIn("pertenece a Telecom Sur, no a Cliente Demo", v.detalle["mensaje"])
        self.assertIn("no existe en la base", self.resultado("X-1").detalle["mensaje"])
        self.assertIn("contrato C2, no al C1", self.resultado("F001-00124").detalle["mensaje"])
        self.assertIn("está anulada", self.resultado("F001-00125").detalle["mensaje"])

    def test_cada_verificacion_queda_guardada_y_en_el_historial(self):
        self.resultado("F001-00123")
        self.resultado(" f001-00119 ")
        vs = list(self.rev.verificaciones_factura.order_by("id"))
        self.assertEqual([(v.numero, v.resultado, v.usuario) for v in vs],
                         [("F001-00123", R.OTRO_CLIENTE, self.j1), ("f001-00119", R.CORRECTA, self.j1)])
        self.assertTrue(all(v.fecha for v in vs))
        detalles = list(self.rev.historial.filter(detalle__startswith="Verificó la factura").values_list("detalle", flat=True))
        self.assertCountEqual(detalles, ["Verificó la factura F001-00123: Pertenece a otro cliente",
                                         "Verificó la factura f001-00119: Correcta"])
        self.assertEqual(verificacion.vigente(self.rev).numero, "f001-00119")

    def test_validaciones_y_permisos(self):
        for numero in ("", "   ", "x" * 51):
            with self.assertRaises(ValidationError):
                verificacion.verificar(self.rev, self.j1, numero)
        with self.assertRaises(PermissionDenied):
            verificacion.verificar(self.rev, self.j2, "F001-00119")
        self.assertFalse(VerificacionFactura.objects.exists())

    def test_un_entregable_entregado_ya_no_se_verifica(self):
        hecho = self.nuevo(self.c1, self.j1, self.s1, "Hecho", E.HECHO)
        with self.assertRaises(ValidationError):
            verificacion.verificar(hecho, self.j1, "F001-00119")

    def test_un_numero_no_correcto_avisa_al_senior(self):
        self.resultado("F001-00123")
        aviso = Notificacion.objects.get(usuario=self.s1, tipo=Notificacion.Tipo.FACTURA)
        self.assertEqual(aviso.entregable, self.rev)
        self.resultado("F001-00119")
        self.assertEqual(Notificacion.objects.filter(tipo=Notificacion.Tipo.FACTURA).count(), 1)


class Caso36AprobacionTests(FacturaBase):
    """HU-30 criterio 3 y caso 36: la factura observada impide aprobar hasta corregirla o justificarla."""

    def test_sin_numero_de_factura_no_se_exige_nada(self):
        aprobar(self.rev, self.s1)
        self.assertEqual(Entregable.objects.get(pk=self.rev.pk).estado, E.LISTO_PARA_ENTREGA)

    def test_numero_inexistente_anulado_o_de_otro_cliente_impide_aprobar(self):
        for numero in ("F999-00001", "F001-00125", "F001-00123", "F001-00124"):
            verificacion.verificar(self.rev, self.j1, numero)
            self.aprobar_falla(texto=f"la factura {numero} quedó")

    def test_corregir_el_numero_permite_aprobar(self):
        verificacion.verificar(self.rev, self.j1, "F001-00123")
        self.aprobar_falla()
        verificacion.verificar(self.rev, self.j1, "F001-00119")
        aprobar(self.rev, self.s1)
        self.assertEqual(Entregable.objects.get(pk=self.rev.pk).estado, E.LISTO_PARA_ENTREGA)

    def test_la_justificacion_del_senior_permite_aprobar_y_queda_en_el_historial(self):
        verificacion.verificar(self.rev, self.j1, "F001-00123")
        v = verificacion.justificar(self.rev, self.s1, "El cliente pidió facturar a su filial; sale en la nota de crédito")
        self.assertEqual((v.justificada_por, v.justificada) , (self.s1, True))
        self.assertIsNotNone(v.justificada_en)
        self.assertTrue(self.rev.historial.filter(detalle__startswith="Justificó la factura F001-00123").exists())
        aprobar(self.rev, self.s1)
        self.assertEqual(Entregable.objects.get(pk=self.rev.pk).estado, E.LISTO_PARA_ENTREGA)

    def test_una_verificacion_nueva_no_correcta_anula_la_justificacion_anterior(self):
        verificacion.verificar(self.rev, self.j1, "F001-00123")
        verificacion.justificar(self.rev, self.s1, "Justificada")
        verificacion.verificar(self.rev, self.j1, "F999-00001")
        self.aprobar_falla(texto="F999-00001")

    def test_la_justificacion_exige_senior_y_texto_y_una_verificacion_observada(self):
        with self.assertRaises(ValidationError):  # nada que justificar
            verificacion.justificar(self.rev, self.s1, "x")
        verificacion.verificar(self.rev, self.j1, "F001-00123")
        for usuario in (self.j1, self.s2):  # un junior y un senior ajeno no justifican
            with self.assertRaises(PermissionDenied):
                verificacion.justificar(self.rev, usuario, "Intento")
        with self.assertRaises(ValidationError):
            verificacion.justificar(self.rev, self.s1, "   ")
        verificacion.justificar(self.rev, self.gerente, "Autorizado por gerencia")
        with self.assertRaises(ValidationError):  # ya justificada
            verificacion.justificar(self.rev, self.s1, "Otra vez")
        verificacion.verificar(self.rev, self.j1, "F001-00119")
        with self.assertRaises(ValidationError):  # correcta: no hay qué justificar
            verificacion.justificar(self.rev, self.s1, "x")

    def test_solo_condiciona_el_paso_a_aprobado(self):
        otro = self.nuevo(self.c1, self.j1, self.s1, "En proceso", E.EN_PROCESO)
        verificacion.verificar(otro, self.j1, "F999-00001")
        servicios.mover(otro, E.VERIFICACION_SENIOR, self.j1)
        self.assertEqual(Entregable.objects.get(pk=otro.pk).estado, E.VERIFICACION_SENIOR)


class VistaTests(FacturaBase):
    def post(self, usuario, datos, entregable=None):
        self.client.force_login(usuario)
        return self.client.post(reverse("entregable_factura", args=[(entregable or self.rev).pk]), datos)

    def test_verificar_desde_el_detalle(self):
        r = self.post(self.j1, {"accion": "verificar", "numero": "F001-00123"})
        self.assertRedirects(r, reverse("entregable_detalle", args=[self.rev.pk]) + "#factura", fetch_redirect_response=False)
        self.assertEqual(verificacion.vigente(self.rev).resultado, R.OTRO_CLIENTE)
        detalle = self.client.get(reverse("entregable_detalle", args=[self.rev.pk]))
        self.assertContains(detalle, "OTRO_CLIENTE")
        self.assertContains(detalle, "pertenece a Telecom Sur")
        self.assertNotContains(detalle, 'name="justificacion"')  # el junior no ve el formulario de justificar

    def test_el_senior_ve_el_formulario_y_justifica(self):
        verificacion.verificar(self.rev, self.j1, "F001-00123")
        self.client.force_login(self.s1)
        self.assertContains(self.client.get(reverse("entregable_detalle", args=[self.rev.pk])), 'name="justificacion"')
        self.post(self.s1, {"accion": "justificar", "justificacion": "Autorizado por el cliente"})
        self.assertTrue(verificacion.vigente(self.rev).justificada)

    def test_un_junior_no_justifica_por_la_vista(self):
        verificacion.verificar(self.rev, self.j1, "F001-00123")
        self.assertEqual(self.post(self.j1, {"accion": "justificar", "justificacion": "x"}).status_code, 403)
        self.assertFalse(verificacion.vigente(self.rev).justificada)

    def test_un_numero_vacio_o_una_accion_invalida_no_guardan_nada(self):
        self.post(self.j1, {"accion": "verificar", "numero": " "})
        self.post(self.j1, {"accion": "otra"})
        self.assertFalse(VerificacionFactura.objects.exists())

    def test_quien_no_ve_el_entregable_recibe_404_y_solo_se_acepta_post(self):
        self.assertEqual(self.post(self.j2, {"accion": "verificar", "numero": "F001-00119"}).status_code, 404)
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(reverse("entregable_factura", args=[self.rev.pk])).status_code, 405)
