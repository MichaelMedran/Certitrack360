import datetime
import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.alertas.models import Notificacion
from apps.alertas.servicios import generar_alertas
from apps.clientes.models import Cliente, Contrato, PlantillaTDR
from apps.conocimiento import servicios as conocimiento
from apps.cuentas.models import Usuario
from apps.entregables import servicios
from apps.entregables.models import Entregable, HistorialEstado, Observacion

E = Entregable.Estado


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        mk = lambda n, r: Usuario.objects.create_user(n, password="x", rol=r)
        cls.admin, cls.gerente = mk("adm", "ADMIN"), mk("ger", "GERENTE")
        cls.s1, cls.s2 = mk("s1", "SENIOR"), mk("s2", "SENIOR")
        cls.j1, cls.j2 = mk("j1", "JUNIOR"), mk("j2", "JUNIOR")
        cls.cliente = Cliente.objects.create(nombre="Cliente Demo", sector="BANCA")
        cls.c1 = Contrato.objects.create(cliente=cls.cliente, numero_contrato="C1", fecha_inicio=datetime.date(2026, 1, 1),
                                         fecha_fin=datetime.date(2027, 1, 1), senior_responsable=cls.s1)
        cls.c1.juniors.set([cls.j1])
        cls.c2 = Contrato.objects.create(cliente=cls.cliente, numero_contrato="C2", fecha_inicio=datetime.date(2026, 1, 1),
                                         fecha_fin=datetime.date(2027, 1, 1), senior_responsable=cls.s2)
        cls.c2.juniors.set([cls.j2])
        cls.plantilla = PlantillaTDR.objects.create(nombre="P", campos_requeridos=[
            {"nombre": "c_periodo", "etiqueta": "Periodo", "tipo": "texto"},
            {"nombre": "c_nivel", "etiqueta": "Nivel", "tipo": "numero"}])
        cls.hoy = timezone.localdate()
        cls.e1 = cls.nuevo(cls.c1, cls.j1, cls.s1, "E1")
        cls.e2 = cls.nuevo(cls.c2, cls.j2, cls.s2, "E2")

    @classmethod
    def nuevo(cls, contrato, junior, senior, titulo, estado=E.A_REALIZAR, dias=10):
        return Entregable.objects.create(
            contrato=contrato, plantilla=cls.plantilla, titulo=titulo, plazo=cls.hoy + datetime.timedelta(days=dias),
            estado=estado, junior_asignado=junior, senior_revisor=senior, creado_por=senior)


class PermisosTests(Base):
    def test_junior_no_accede_a_administracion(self):
        self.client.force_login(self.j1)
        for ent in ("clientes", "contratos", "plantillas"):
            self.assertEqual(self.client.get(reverse("adm_lista", args=[ent])).status_code, 403)
            self.assertEqual(self.client.get(reverse("adm_nuevo", args=[ent])).status_code, 403)
        self.assertEqual(self.client.get(reverse("administracion")).status_code, 403)

    def test_senior_no_accede_a_administracion(self):
        self.client.force_login(self.s1)
        self.assertEqual(self.client.get(reverse("administracion")).status_code, 403)

    def test_gerente_si_accede(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(reverse("adm_lista", args=["contratos"])).status_code, 200)

    def test_visibilidad_por_rol(self):
        def titulos(user):
            self.client.force_login(user)
            return {e.titulo for e in self.client.get(reverse("entregables")).context["entregables"]}
        self.assertEqual(titulos(self.j1), {"E1"})
        self.assertEqual(titulos(self.s1), {"E1"})
        self.assertEqual(titulos(self.gerente), {"E1", "E2"})
        self.assertEqual(titulos(self.admin), {"E1", "E2"})

    def test_detalle_ajeno_da_404(self):
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(reverse("entregable_detalle", args=[self.e2.pk])).status_code, 404)
        self.client.force_login(self.s1)
        self.assertEqual(self.client.get(reverse("entregable_detalle", args=[self.e2.pk])).status_code, 404)

    def test_calendario_filtra_por_rol(self):
        def eventos(user):
            self.client.force_login(user)
            return {ev["id"] for ev in self.client.get(reverse("calendario_eventos")).json()}
        self.assertEqual(eventos(self.j1), {self.e1.pk})
        self.assertEqual(eventos(self.s2), {self.e2.pk})
        self.assertEqual(eventos(self.gerente), {self.e1.pk, self.e2.pk})

    def test_login_requerido(self):
        self.assertEqual(self.client.get(reverse("tablero")).status_code, 302)
        self.assertEqual(self.client.get(reverse("calendario_eventos")).status_code, 302)

    def test_junior_no_puede_crear_entregables(self):
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(reverse("entregable_nuevo")).status_code, 403)

    def test_cuatro_roles_inician_sesion(self):
        for u in (self.j1, self.s1, self.gerente, self.admin):
            self.assertTrue(self.client.login(username=u.username, password="x"))
            self.assertEqual(self.client.get(reverse("inicio")).status_code, 200)


class PokaYokeTests(Base):
    def datos(self, **extra):
        d = {"plantilla": self.plantilla.pk, "contrato": self.c1.pk, "titulo": "Nuevo", "junior_asignado": self.j1.pk,
             "plazo": (self.hoy + datetime.timedelta(days=5)).isoformat(), "c_periodo": "Ene-2026", "c_nivel": "3"}
        d.update(extra)
        return d

    def post(self, **extra):
        self.client.force_login(self.s1)
        return self.client.post(reverse("entregable_nuevo"), self.datos(**extra))

    def test_creacion_valida(self):
        r = self.post()
        self.assertEqual(r.status_code, 302)
        e = Entregable.objects.get(titulo="Nuevo")
        self.assertEqual(e.senior_revisor, self.s1)
        self.assertTrue(Notificacion.objects.filter(usuario=self.j1, tipo="ASIGNACION").exists())
        self.assertEqual(e.historial.count(), 1)

    def test_campo_obligatorio_faltante_indica_cual(self):
        r = self.post(c_periodo="")
        self.assertEqual(Entregable.objects.filter(titulo="Nuevo").count(), 0)
        self.assertContains(r, "Falta completar el campo «Periodo».")

    def test_varios_faltantes(self):
        r = self.post(c_periodo="", c_nivel="")
        self.assertContains(r, "«Periodo»")
        self.assertContains(r, "«Nivel»")

    def test_plazo_pasado(self):
        r = self.post(plazo=(self.hoy - datetime.timedelta(days=1)).isoformat())
        self.assertContains(r, "El plazo no puede ser anterior a hoy.")
        self.assertFalse(Entregable.objects.filter(titulo="Nuevo").exists())

    def test_sin_contrato(self):
        r = self.post(contrato="")
        self.assertContains(r, "Falta elegir el contrato.")

    def test_senior_no_crea_en_contrato_ajeno(self):
        r = self.post(contrato=self.c2.pk, junior_asignado=self.j2.pk)
        self.assertFalse(Entregable.objects.filter(titulo="Nuevo").exists())
        self.assertEqual(r.status_code, 200)

    def test_junior_de_otro_contrato(self):
        r = self.post(junior_asignado=self.j2.pk)
        self.assertContains(r, "no está asignado al contrato")


class FlujoTests(Base):
    def test_transicion_no_permitida(self):
        with self.assertRaises(ValidationError):
            servicios.mover(self.e1, E.HECHO, self.s1)
        with self.assertRaises(ValidationError):
            servicios.mover(self.e1, E.VERIFICACION_SENIOR, self.j1)  # salta EN_PROCESO
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.estado, E.A_REALIZAR)

    def test_camino_feliz_registra_historial(self):
        servicios.mover(self.e1, E.EN_PROCESO, self.j1)
        servicios.mover(self.e1, E.VERIFICACION_SENIOR, self.j1)
        servicios.mover(self.e1, E.LISTO_PARA_ENTREGA, self.s1)
        servicios.mover(self.e1, E.HECHO, self.gerente)
        self.assertEqual(HistorialEstado.objects.filter(entregable=self.e1).count(), 4)

    def test_junior_ajeno_no_mueve(self):
        with self.assertRaises(PermissionDenied):
            servicios.mover(self.e1, E.EN_PROCESO, self.j2)

    def test_junior_no_aprueba(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "V", E.VERIFICACION_SENIOR)
        with self.assertRaises(PermissionDenied):
            servicios.mover(e, E.LISTO_PARA_ENTREGA, self.j1)

    def test_senior_ajeno_no_aprueba(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "V", E.VERIFICACION_SENIOR)
        with self.assertRaises(PermissionDenied):
            servicios.mover(e, E.LISTO_PARA_ENTREGA, self.s2)

    def test_devolver_exige_observacion(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "V", E.VERIFICACION_SENIOR)
        with self.assertRaises(ValidationError):
            servicios.mover(e, E.EN_PROCESO, self.s1)
        with self.assertRaises(ValidationError):
            servicios.mover(e, E.EN_PROCESO, self.s1, tipo_error="FORMATO", descripcion="  ")
        servicios.mover(e, E.EN_PROCESO, self.s1, tipo_error="FORMATO", descripcion="Falta numeración")
        self.assertEqual(e.observaciones.count(), 1)
        self.assertTrue(Notificacion.objects.filter(usuario=self.j1, tipo="OBSERVACION").exists())

    def test_api_rechaza_transicion_invalida(self):
        self.client.force_login(self.j1)
        r = self.client.post(reverse("tablero_mover", args=[self.e1.pk]), json.dumps({"estado": "HECHO"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.estado, E.A_REALIZAR)

    def test_api_acepta_transicion_valida_y_no_toca_ajenos(self):
        self.client.force_login(self.j1)
        r = self.client.post(reverse("tablero_mover", args=[self.e1.pk]), json.dumps({"estado": "EN_PROCESO"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        r = self.client.post(reverse("tablero_mover", args=[self.e2.pk]), json.dumps({"estado": "EN_PROCESO"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 404)


class AlertasTests(Base):
    def test_una_notificacion_por_umbral(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Pronto", dias=2)
        generar_alertas(self.hoy)
        generar_alertas(self.hoy)  # idempotente
        self.assertEqual(Notificacion.objects.filter(entregable=e, tipo="VENCIMIENTO", usuario=self.j1).count(), 1)
        generar_alertas(self.hoy + datetime.timedelta(days=2))  # llega el día: nuevo umbral (0)
        self.assertEqual(Notificacion.objects.filter(entregable=e, tipo="VENCIMIENTO", usuario=self.j1).count(), 2)

    def test_lejanos_hechos_y_vencidos_no_alertan(self):
        self.nuevo(self.c1, self.j1, self.s1, "Lejos", dias=30)
        self.nuevo(self.c1, self.j1, self.s1, "Hecho", estado=E.HECHO, dias=1)
        self.nuevo(self.c1, self.j1, self.s1, "Vencido", dias=-3)
        self.assertEqual(generar_alertas(self.hoy), 0)

    def test_aviso_no_leidas_en_pantalla(self):
        Notificacion.objects.create(usuario=self.j1, entregable=self.e1, tipo="ASIGNACION", mensaje="x")
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(reverse("inicio")).context["no_leidas"], 1)


class ConocimientoYSeedTests(TestCase):
    def test_seed_idempotente_y_chatbot_cita_caso(self):
        call_command("seed_demo", "--reset", verbosity=0)
        call_command("seed_demo", verbosity=0)
        self.assertEqual(Entregable.objects.count(), 30)
        self.assertEqual(len({e.estado for e in Entregable.objects.all()}), 5)
        self.client.login(username="gerente_demo", password="demo1234")
        r = self.client.get(reverse("asistente"), {"q": "falta el periodo reportado en el informe"})
        self.assertTrue(r.context["casos"])
        self.assertContains(r, "Caso 1")
        self.assertIn("periodo", r.context["casos"][0]["leccion"].problema.lower())

    def test_busqueda_sin_resultados(self):
        self.assertEqual(conocimiento.buscar("xyzzy"), [])
