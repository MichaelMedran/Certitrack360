"""SDD del Sprint 3, hito S3-H4: alerta de urgencia fuera de horario (RF-43, HU-28). Caso clave 33 de la §13.

Criterio de aceptación: «Activar avisa a guardia y responsables con "URGENTE", cliente, naturaleza y plazo; la lectura y la
aceptación quedan registradas».
  1. Activar avisa a guardia y responsables, una sola vez        -> ActivarTests
  2. El aviso dice URGENTE, cliente, naturaleza y plazo           -> AvisoTests
  3. La lectura queda registrada (y la franja desaparece)         -> LecturaTests, FranjaTests
  4. La aceptación queda registrada, una sola persona             -> AceptarTests
  5. Selector al registrar y al activar desde el detalle          -> CrearEntregableUrgenteTests, DetalleTests
"""
import datetime
import zoneinfo

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.alertas.models import Notificacion
from apps.cuentas.models import Usuario
from apps.entregables import extensiones
from apps.entregables.models import Entregable, HistorialEstado
from apps.entregables.tests import Base
from apps.entregables.visibilidad import entregables_visibles

from . import servicios
from .models import AlertaUrgente, LecturaAlerta

E = Entregable.Estado
LIMA = zoneinfo.ZoneInfo("America/Lima")


def lima(anio, mes, dia, hora, minuto=0):
    return datetime.datetime(anio, mes, dia, hora, minuto, tzinfo=LIMA)


class UrgenciasBase(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.guardia = Usuario.objects.create_user("guardia", password="x", rol="JUNIOR", de_guardia=True)
        cls.revisor = Usuario.objects.create_user("rev", password="x", rol="SENIOR")
        cls.e1.senior_revisor = cls.revisor
        cls.e1.save(update_fields=["senior_revisor"])
        cls.plazo = timezone.now() + datetime.timedelta(days=1)

    def activar(self, usuario=None, **extra):
        datos = {"naturaleza": "Caída del servicio de carga", "plazo_esperado": self.plazo}
        datos.update(extra)
        return servicios.activar(usuario or self.s1, self.e1, **datos)

    def avisos(self, usuario):
        return list(Notificacion.objects.filter(usuario=usuario, tipo=Notificacion.Tipo.URGENTE))


# ------------------------------------------------------------------ 1 y 2: activar avisa

class ActivarTests(UrgenciasBase):
    def test_avisa_a_guardia_y_responsables_sin_repetir_y_sin_quien_activa(self):
        alerta = self.activar(self.gerente)
        self.assertEqual(
            set(alerta.destinatarios.all()), {self.guardia, self.s1, self.revisor, self.j1},
        )
        for u in (self.guardia, self.s1, self.revisor, self.j1):
            self.assertEqual(len(self.avisos(u)), 1, u.username)
        self.assertEqual(self.avisos(self.gerente), [])  # quien activa no se avisa a sí mismo
        self.assertEqual(self.avisos(self.j2), [])  # ni quien no tiene que ver

    def test_una_persona_con_dos_funciones_recibe_un_solo_aviso(self):
        self.e1.senior_revisor = self.s1  # el senior responsable del contrato es también el revisor
        self.e1.save(update_fields=["senior_revisor"])
        Usuario.objects.filter(pk=self.s1.pk).update(de_guardia=True)  # y además está de guardia
        alerta = self.activar(self.gerente)
        self.assertEqual(set(alerta.destinatarios.all()), {self.s1, self.guardia, self.j1})
        self.assertEqual(len(self.avisos(self.s1)), 1)

    def test_quien_activa_y_esta_de_guardia_no_se_avisa(self):
        self.activar(self.s1)
        self.assertEqual(self.avisos(self.s1), [])
        self.assertEqual(len(self.avisos(self.guardia)), 1)

    def test_la_guardia_inactiva_no_recibe_aviso(self):
        Usuario.objects.filter(pk=self.guardia.pk).update(is_active=False)
        alerta = self.activar()
        self.assertNotIn(self.guardia, alerta.destinatarios.all())
        self.assertEqual(self.avisos(self.guardia), [])

    def test_activar_dos_veces_no_duplica_avisos_ni_alertas(self):
        self.activar()
        from django.core.exceptions import ValidationError
        with self.assertRaisesMessage(ValidationError, "ya tiene una alerta urgente abierta"):
            self.activar()
        self.assertEqual(AlertaUrgente.objects.filter(entregable=self.e1).count(), 1)
        self.assertEqual(len(self.avisos(self.guardia)), 1)

    def test_queda_en_el_historial(self):
        self.activar()
        self.assertTrue(HistorialEstado.objects.filter(entregable=self.e1, detalle__startswith="Activó la alerta urgente").exists())

    def test_reglas_de_los_datos(self):
        from django.core.exceptions import ValidationError
        casos = {
            "sin naturaleza": ({"naturaleza": "   "}, "naturaleza"),
            "sin plazo": ({"plazo_esperado": None}, "plazo esperado"),
            "plazo pasado": ({"plazo_esperado": timezone.now() - datetime.timedelta(minutes=1)}, "futuras"),
        }
        for nombre, (extra, texto) in casos.items():
            with self.subTest(nombre):
                with self.assertRaisesMessage(ValidationError, texto):
                    self.activar(**extra)
        self.assertFalse(AlertaUrgente.objects.exists())
        self.assertFalse(Notificacion.objects.filter(tipo=Notificacion.Tipo.URGENTE).exists())

    def test_no_se_activa_en_un_entregable_entregado(self):
        from django.core.exceptions import ValidationError
        Entregable.objects.filter(pk=self.e1.pk).update(estado=E.HECHO)
        self.e1.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "ya entregado"):
            self.activar()

    def test_quien_puede_activar(self):
        from django.core.exceptions import PermissionDenied
        for usuario in (self.j1, self.s2, self.guardia):  # junior, senior ajeno, guardia sin ser responsable
            with self.subTest(usuario.username):
                with self.assertRaises(PermissionDenied):
                    self.activar(usuario)
        for usuario in (self.s1, self.revisor, self.gerente, self.admin):
            with self.subTest(usuario.username):
                AlertaUrgente.objects.all().delete()
                self.assertTrue(self.activar(usuario).abierta)


class AvisoTests(UrgenciasBase):
    def test_el_aviso_empieza_con_urgente_y_dice_cliente_naturaleza_y_plazo(self):
        plazo = lima(2026, 11, 12, 18, 0)
        servicios.activar(self.s1, self.e1, "Caída del servicio de carga", plazo, ahora=lima(2026, 11, 10, 8, 0))
        aviso = self.avisos(self.j1)[0]
        self.assertTrue(aviso.mensaje.startswith("URGENTE"))
        self.assertIn("Cliente Demo", aviso.mensaje)
        self.assertIn("Caída del servicio de carga", aviso.mensaje)
        self.assertIn("12/11/2026 18:00", aviso.mensaje)
        self.assertEqual(aviso.entregable, self.e1)
        self.assertEqual(aviso.destino, reverse("entregable_detalle", args=[self.e1.pk]))  # enlace al entregable
        self.assertFalse(aviso.leida)

    def test_una_naturaleza_larga_no_rompe_el_aviso(self):
        alerta = self.activar(naturaleza="x" * 900)
        mensaje = self.avisos(self.j1)[0].mensaje
        self.assertLessEqual(len(mensaje), 255)
        self.assertTrue(mensaje.startswith("URGENTE · Cliente Demo"))
        self.assertTrue(mensaje.endswith("plazo esperado " + timezone.localtime(alerta.plazo_esperado).strftime("%d/%m/%Y %H:%M")))

    def test_sin_servidor_de_correo_no_se_envia_nada(self):
        self.activar()
        self.assertEqual(mail.outbox, [])

    @override_settings(EMAIL_HOST="localhost")
    def test_con_servidor_de_correo_se_envia_urgente_a_quien_tiene_direccion(self):
        Usuario.objects.filter(pk__in=[self.j1.pk, self.guardia.pk]).update(email="a@ejemplo.test")
        with self.captureOnCommitCallbacks(execute=True):
            self.activar()
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(mail.outbox[0].subject.startswith("URGENTE: "))
        self.assertEqual(set(mail.outbox[0].to), {"a@ejemplo.test"})

    @override_settings(EMAIL_HOST="localhost")
    def test_un_fallo_del_correo_no_impide_la_alerta(self):
        Usuario.objects.filter(pk=self.j1.pk).update(email="a@ejemplo.test")
        from unittest import mock
        with mock.patch("apps.urgencias.servicios.send_mail", side_effect=OSError("sin red")):
            with self.captureOnCommitCallbacks(execute=True):
                alerta = self.activar()
        self.assertTrue(AlertaUrgente.objects.filter(pk=alerta.pk).exists())
        self.assertEqual(len(self.avisos(self.j1)), 1)


class FueraDeHorarioTests(UrgenciasBase):
    def test_horario_laboral_por_defecto(self):
        casos = [
            (lima(2026, 11, 10, 10), False),  # martes, en horario
            (lima(2026, 11, 10, 9, 0), False),  # justo al abrir
            (lima(2026, 11, 10, 8, 59), True),  # antes de abrir
            (lima(2026, 11, 10, 18, 0), True),  # al cerrar ya es fuera de horario
            (lima(2026, 11, 14, 11), True),  # sábado
            (lima(2026, 11, 15, 11), True),  # domingo
        ]
        for momento, esperado in casos:
            with self.subTest(momento=momento):
                self.assertIs(servicios.esta_fuera_de_horario(momento), esperado)

    def test_se_guarda_al_activar_con_la_hora_de_lima(self):
        # 01:00 UTC del miércoles 11 = martes 10 a las 20:00 en Lima: fuera de horario.
        ahora = datetime.datetime(2026, 11, 11, 1, 0, tzinfo=datetime.timezone.utc)
        alerta = servicios.activar(self.s1, self.e1, "Urgencia", lima(2026, 11, 12, 18), ahora=ahora)
        self.assertTrue(alerta.fuera_de_horario)

    def test_el_horario_es_configurable(self):
        import datetime as dt
        with override_settings(HORARIO_LABORAL=({6, 7}, dt.time(0, 0), dt.time(23, 59))):
            self.assertFalse(servicios.esta_fuera_de_horario(lima(2026, 11, 14, 11)))
            self.assertTrue(servicios.esta_fuera_de_horario(lima(2026, 11, 10, 11)))


# ------------------------------------------------------------------ 3: lectura y franja

class LecturaTests(UrgenciasBase):
    def test_la_lectura_registra_quien_y_cuando(self):
        alerta = self.activar()
        self.client.force_login(self.j1)
        r = self.client.post(reverse("urgencia_leer", args=[alerta.pk]), {"volver": "/entregables/"})
        self.assertRedirects(r, "/entregables/", fetch_redirect_response=False)
        lectura = LecturaAlerta.objects.get(alerta=alerta, usuario=self.j1)
        self.assertLessEqual(abs((timezone.now() - lectura.leida_en).total_seconds()), 30)

    def test_confirmar_dos_veces_deja_una_sola_lectura(self):
        alerta = self.activar()
        self.client.force_login(self.j1)
        for _ in range(2):
            self.client.post(reverse("urgencia_leer", args=[alerta.pk]))
        self.assertEqual(LecturaAlerta.objects.filter(alerta=alerta, usuario=self.j1).count(), 1)

    def test_quien_no_es_destinatario_ni_senior_del_entregable_no_puede(self):
        alerta = self.activar()
        self.client.force_login(self.j2)  # no ve el entregable: 404
        self.assertEqual(self.client.post(reverse("urgencia_leer", args=[alerta.pk])).status_code, 404)
        self.client.force_login(self.s2)
        self.assertEqual(self.client.post(reverse("urgencia_aceptar", args=[alerta.pk])).status_code, 404)
        self.assertFalse(LecturaAlerta.objects.exists())

    def test_ve_pero_no_puede_da_403(self):
        # Un junior de apoyo ve el entregable pero no es destinatario: 403.
        from apps.entregables.models import ResponsableApoyo
        ResponsableApoyo.objects.create(entregable=self.e1, usuario=self.j2, asignado_por=self.s1)
        alerta = self.activar()
        self.assertTrue(entregables_visibles(self.j2).filter(pk=self.e1.pk).exists())
        self.client.force_login(self.j2)
        self.assertEqual(self.client.post(reverse("urgencia_leer", args=[alerta.pk])).status_code, 403)

    def test_solo_post_y_con_sesion(self):
        alerta = self.activar()
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(reverse("urgencia_leer", args=[alerta.pk])).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(reverse("urgencia_leer", args=[alerta.pk])).status_code, 302)
        self.assertFalse(LecturaAlerta.objects.exists())

    def test_un_enlace_externo_de_vuelta_se_ignora(self):
        alerta = self.activar()
        self.client.force_login(self.j1)
        r = self.client.post(reverse("urgencia_leer", args=[alerta.pk]), {"volver": "https://externo.example/"})
        self.assertRedirects(r, reverse("entregable_detalle", args=[self.e1.pk]), fetch_redirect_response=False)


class FranjaTests(UrgenciasBase):
    def test_los_destinatarios_ven_la_franja_en_todas_las_pantallas_hasta_leer(self):
        alerta = self.activar()
        pantallas = [reverse("inicio"), reverse("entregables"), reverse("notificaciones"), reverse("calendario")]
        for usuario in (self.j1, self.revisor, self.guardia):
            self.client.force_login(usuario)
            for url in pantallas:
                with self.subTest(usuario=usuario.username, url=url):
                    r = self.client.get(url)
                    self.assertContains(r, "franja-urgente")
                    self.assertContains(r, "URGENTE")
                    self.assertContains(r, "Cliente Demo")
                    self.assertContains(r, "Caída del servicio de carga")
                    self.assertContains(r, reverse("urgencia_leer", args=[alerta.pk]))
        self.client.force_login(self.j1)
        self.client.post(reverse("urgencia_leer", args=[alerta.pk]))
        for url in pantallas:
            self.assertNotContains(self.client.get(url), "franja-urgente")
        # Quien aún no leyó la sigue viendo.
        self.client.force_login(self.guardia)
        self.assertContains(self.client.get(reverse("inicio")), "franja-urgente")

    def test_quien_no_es_destinatario_no_la_ve_y_tampoco_quien_activa(self):
        self.activar(self.s1)
        for usuario in (self.s1, self.j2, self.s2, self.gerente):
            self.client.force_login(usuario)
            with self.subTest(usuario.username):
                self.assertNotContains(self.client.get(reverse("inicio")), "franja-urgente")

    def test_la_guardia_sin_acceso_al_entregable_no_recibe_un_enlace_roto(self):
        alerta = self.activar()
        self.client.force_login(self.guardia)
        r = self.client.get(reverse("inicio"))
        self.assertNotContains(r, reverse("entregable_detalle", args=[self.e1.pk]))
        self.assertContains(r, self.e1.codigo)
        # Y puede confirmar y volver sin error.
        r = self.client.post(reverse("urgencia_leer", args=[alerta.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get(r.url).status_code, 200)

    def test_la_franja_desaparece_al_cerrarse_la_alerta(self):
        alerta = self.activar()
        AlertaUrgente.objects.filter(pk=alerta.pk).update(cerrada_en=timezone.now())
        self.client.force_login(self.j1)
        self.assertNotContains(self.client.get(reverse("inicio")), "franja-urgente")

    def test_sin_alertas_y_sin_sesion_no_hay_franja(self):
        self.assertNotContains(self.client.get(reverse("login")), "franja-urgente")
        self.client.force_login(self.j1)
        self.assertNotContains(self.client.get(reverse("inicio")), "franja-urgente")

    def test_el_texto_de_la_naturaleza_se_escapa(self):
        self.activar(naturaleza="<script>alert(1)</script>")
        self.client.force_login(self.j1)
        r = self.client.get(reverse("inicio"))
        self.assertNotContains(r, "<script>alert(1)</script>")


# ------------------------------------------------------------------ 4: aceptación

class AceptarTests(UrgenciasBase):
    def test_aceptar_registra_quien_y_cuando_y_cierra(self):
        alerta = self.activar()
        self.client.force_login(self.guardia)
        self.client.post(reverse("urgencia_aceptar", args=[alerta.pk]))
        alerta.refresh_from_db()
        self.assertEqual(alerta.aceptada_por, self.guardia)
        self.assertIsNotNone(alerta.aceptada_en)
        self.assertIsNotNone(alerta.cerrada_en)
        self.assertFalse(alerta.abierta)
        self.assertTrue(LecturaAlerta.objects.filter(alerta=alerta, usuario=self.guardia).exists())
        self.assertTrue(HistorialEstado.objects.filter(entregable=self.e1, detalle__startswith="Aceptó el caso").exists())

    def test_solo_una_persona_acepta(self):
        alerta = self.activar()
        self.client.force_login(self.guardia)
        self.client.post(reverse("urgencia_aceptar", args=[alerta.pk]))
        self.client.force_login(self.revisor)
        r = self.client.post(reverse("urgencia_aceptar", args=[alerta.pk]), follow=True)
        self.assertContains(r, "ya fue aceptado por")
        alerta.refresh_from_db()
        self.assertEqual(alerta.aceptada_por, self.guardia)

    def test_aceptar_una_alerta_cerrada_por_entrega_se_rechaza(self):
        from django.core.exceptions import ValidationError
        alerta = self.activar()
        servicios.cerrar_al_entregar(self.e1)
        with self.assertRaisesMessage(ValidationError, "ya está cerrada"):
            servicios.aceptar(self.j1, alerta)

    def test_el_gerente_y_el_senior_del_entregable_aceptan_sin_ser_destinatarios(self):
        for usuario in (self.gerente, self.admin):
            with self.subTest(usuario.username):
                AlertaUrgente.objects.all().delete()
                alerta = self.activar(self.s1)
                self.assertNotIn(usuario, alerta.destinatarios.all())
                self.assertEqual(servicios.aceptar(usuario, alerta).aceptada_por, usuario)

    def test_un_junior_no_destinatario_no_acepta(self):
        from django.core.exceptions import PermissionDenied
        alerta = self.activar()
        with self.assertRaises(PermissionDenied):
            servicios.aceptar(self.j2, alerta)


class CierreAlEntregarTests(UrgenciasBase):
    def test_la_extension_esta_registrada(self):
        self.assertIn(servicios.al_mover, extensiones._al_mover)

    def test_al_pasar_a_entregado_se_cierra_la_alerta(self):
        alerta = self.activar()
        servicios.al_mover(self.e1, E.LISTO_PARA_ENTREGA, E.HECHO, self.s1, {})
        alerta.refresh_from_db()
        self.assertIsNotNone(alerta.cerrada_en)
        self.assertIsNone(alerta.aceptada_por)

    def test_otros_pasos_no_la_cierran(self):
        alerta = self.activar()
        servicios.al_mover(self.e1, E.A_REALIZAR, E.EN_PROCESO, self.j1, {})
        alerta.refresh_from_db()
        self.assertTrue(alerta.abierta)

    def test_con_la_alerta_cerrada_se_puede_activar_otra(self):
        self.activar()
        servicios.cerrar_al_entregar(self.e1)
        self.assertTrue(self.activar().abierta)
        self.assertEqual(AlertaUrgente.objects.filter(entregable=self.e1).count(), 2)


# ------------------------------------------------------------------ 5: detalle y registro

class DetalleTests(UrgenciasBase):
    def post_activar(self, usuario, **extra):
        self.client.force_login(usuario)
        local = timezone.localtime(self.plazo).strftime("%Y-%m-%dT%H:%M")
        datos = {"naturaleza": "Caída del servicio de carga", "plazo_esperado": local}
        datos.update(extra)
        return self.client.post(reverse("entregable_urgencia", args=[self.e1.pk]), datos)

    def test_el_senior_activa_desde_el_detalle(self):
        r = self.post_activar(self.s1)
        self.assertRedirects(r, reverse("entregable_detalle", args=[self.e1.pk]) + "#urgencia", fetch_redirect_response=False)
        alerta = AlertaUrgente.objects.get(entregable=self.e1)
        self.assertEqual(alerta.activada_por, self.s1)
        self.assertEqual(len(self.avisos(self.j1)), 1)

    def test_el_detalle_muestra_la_alerta_con_sus_datos_y_botones(self):
        self.activar()
        self.client.force_login(self.j1)
        r = self.client.get(reverse("entregable_detalle", args=[self.e1.pk]))
        self.assertContains(r, "Alerta urgente")
        self.assertContains(r, "Caída del servicio de carga")
        self.assertContains(r, "0 de 3 destinatarios confirmaron")
        self.assertContains(r, "Confirmar lectura")
        self.assertContains(r, "Aceptar el caso")
        self.assertNotContains(r, "Activar y avisar")  # el junior no activa
        self.client.post(reverse("urgencia_leer", args=[AlertaUrgente.objects.get().pk]))
        r = self.client.get(reverse("entregable_detalle", args=[self.e1.pk]))
        self.assertContains(r, "1 de 3 destinatarios confirmaron")

    def test_el_senior_ve_el_formulario_de_activar_y_el_junior_no(self):
        self.client.force_login(self.s1)
        self.assertContains(self.client.get(reverse("entregable_detalle", args=[self.e1.pk])), "Activar y avisar")
        self.client.force_login(self.j1)
        r = self.client.get(reverse("entregable_detalle", args=[self.e1.pk]))
        self.assertNotContains(r, "Activar y avisar")
        self.assertNotContains(r, 'id="urgencia"')  # sin alerta y sin permiso, la sección no aparece

    def test_validaciones_desde_el_detalle(self):
        for extra, texto in (({"naturaleza": ""}, "naturaleza de la urgencia"), ({"plazo_esperado": ""}, "plazo esperado"),
                             ({"plazo_esperado": "2020-01-01T10:00"}, "futuras")):
            with self.subTest(extra=extra):
                r = self.post_activar(self.s1, **extra)
                self.assertEqual(r.status_code, 302)
                self.assertContains(self.client.get(r.url), texto)
        self.assertFalse(AlertaUrgente.objects.exists())

    def test_permisos_al_activar(self):
        self.assertEqual(self.post_activar(self.j1).status_code, 403)  # lo ve pero no puede
        self.assertEqual(self.post_activar(self.s2).status_code, 404)  # no lo ve
        self.assertEqual(self.post_activar(self.j2).status_code, 404)
        self.assertFalse(AlertaUrgente.objects.exists())
        self.client.force_login(self.s1)
        self.assertEqual(self.client.get(reverse("entregable_urgencia", args=[self.e1.pk])).status_code, 405)

    def test_tablero_y_lista_marcan_la_tarjeta_urgente(self):
        self.client.force_login(self.s1)
        self.assertNotContains(self.client.get(reverse("entregables")), "marca-urgente")
        self.activar()
        self.assertContains(self.client.get(reverse("entregables")), "marca-urgente")

    def test_enriquecer_deja_la_marca_con_consultas_por_lote(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        self.activar()
        with CaptureQueriesContext(connection) as c:
            filas = servicios.enriquecer([self.e1, self.e2])
        self.assertEqual(len(c), 1)
        self.assertEqual([f.alerta_urgente_abierta for f in filas], [True, False])


class DatosParaLaPrioridadTests(UrgenciasBase):
    """Lo que lee S3-H3 (prioridad calculada): una alerta abierta hace Alta la prioridad."""

    def test_funciones_de_lectura(self):
        self.assertEqual(servicios.ids_con_alerta_abierta(), set())
        self.assertIsNone(servicios.abierta_de(self.e1))
        alerta = self.activar()
        self.assertEqual(servicios.ids_con_alerta_abierta(), {self.e1.pk})
        self.assertEqual(servicios.ids_con_alerta_abierta([self.e2]), set())
        self.assertEqual(servicios.ids_con_alerta_abierta([self.e1.pk, self.e2.pk]), {self.e1.pk})
        self.assertEqual(servicios.abierta_de(self.e1), alerta)
        self.assertEqual(list(Entregable.objects.filter(servicios.condicion_alerta_abierta())), [self.e1])
        self.assertEqual(list(AlertaUrgente.objects.abiertas()), [alerta])
        servicios.cerrar_al_entregar(self.e1)
        self.assertEqual(servicios.ids_con_alerta_abierta(), set())
        self.assertEqual(list(Entregable.objects.filter(servicios.condicion_alerta_abierta())), [])


class RestriccionesTests(UrgenciasBase):
    def test_la_base_de_datos_impide_dos_alertas_abiertas_y_dos_lecturas(self):
        from django.db import IntegrityError, transaction
        alerta = self.activar()
        with self.assertRaises(IntegrityError), transaction.atomic():
            AlertaUrgente.objects.create(
                entregable=self.e1, naturaleza="otra", plazo_esperado=self.plazo, activada_por=self.s1)
        LecturaAlerta.objects.create(alerta=alerta, usuario=self.j1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            LecturaAlerta.objects.create(alerta=alerta, usuario=self.j1)


# ------------------------------------------------------------------ 5: al registrar el entregable

class CrearEntregableUrgenteTests(UrgenciasBase):
    def datos(self, **extra):
        d = {"plantilla": self.plantilla.pk, "contrato": self.c1.pk, "titulo": "Urgente nuevo", "junior_asignado": self.j1.pk,
             "id_tdr": "TDR-9", "fecha_recepcion": self.hoy.isoformat(),
             "plazo": (self.hoy + datetime.timedelta(days=9)).isoformat(), "c_periodo": "Octubre 2026", "c_nivel": "3"}
        d.update(extra)
        return d

    def urgente(self, **extra):
        local = timezone.localtime(self.plazo).strftime("%Y-%m-%dT%H:%M")
        return self.datos(**{"prioridad": "URGENTE", "naturaleza": "Caída del servicio", "plazo_esperado": local, **extra})

    def test_el_formulario_ofrece_el_selector(self):
        self.client.force_login(self.s1)
        r = self.client.get(reverse("entregable_nuevo"), {"plantilla": self.plantilla.pk})
        self.assertContains(r, "Urgente – fuera de horario")
        self.assertContains(r, "Normal")

    def test_urgente_crea_la_alerta_y_avisa(self):
        self.client.force_login(self.s1)
        r = self.client.post(reverse("entregable_nuevo"), self.urgente())
        self.assertEqual(r.status_code, 302)
        e = Entregable.objects.get(titulo="Urgente nuevo")
        alerta = AlertaUrgente.objects.get(entregable=e)
        self.assertEqual(alerta.activada_por, self.s1)
        self.assertEqual(set(alerta.destinatarios.all()), {self.guardia, self.j1})  # s1 crea y es el revisor por omisión
        for u in (self.guardia, self.j1):
            urgentes = Notificacion.objects.filter(usuario=u, tipo=Notificacion.Tipo.URGENTE, entregable=e)
            self.assertEqual(urgentes.count(), 1)
            self.assertTrue(urgentes[0].mensaje.startswith("URGENTE"))
        # El junior, además del aviso de asignación, recibe el URGENTE: una sola vez cada uno.
        self.assertEqual(Notificacion.objects.filter(usuario=self.j1, entregable=e).count(), 2)

    def test_normal_no_crea_alerta(self):
        self.client.force_login(self.s1)
        for extra in ({}, {"prioridad": "NORMAL"}, {"prioridad": "NORMAL", "naturaleza": "ignorada"}):
            with self.subTest(extra=extra):
                self.client.post(reverse("entregable_nuevo"), self.datos(titulo="Normal " + str(len(extra)), **extra))
        self.assertFalse(AlertaUrgente.objects.exists())
        self.assertFalse(Notificacion.objects.filter(tipo=Notificacion.Tipo.URGENTE).exists())

    def test_urgente_exige_naturaleza_y_plazo_futuro(self):
        self.client.force_login(self.s1)
        casos = (({"naturaleza": ""}, "naturaleza de la urgencia"), ({"plazo_esperado": ""}, "plazo esperado"),
                 ({"plazo_esperado": "2020-01-01T10:00"}, "futuras"), ({"plazo_esperado": "mañana"}, "formato válido"))
        for extra, texto in casos:
            with self.subTest(extra=extra):
                r = self.client.post(reverse("entregable_nuevo"), self.urgente(**extra))
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, texto)
        self.assertFalse(Entregable.objects.filter(titulo="Urgente nuevo").exists())  # nada a medias
        self.assertFalse(AlertaUrgente.objects.exists())

    def test_una_prioridad_desconocida_se_rechaza(self):
        self.client.force_login(self.s1)
        r = self.client.post(reverse("entregable_nuevo"), self.datos(prioridad="CRITICA"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Elija una prioridad")


class PersonalGuardiaTests(UrgenciasBase):
    def post(self, usuario, objetivo, valor):
        self.client.force_login(usuario)
        return self.client.post(reverse("personal"), {"accion": "guardia", "usuario": objetivo.pk, "de_guardia": valor})

    def test_gerente_y_admin_marcan_y_quitan(self):
        for actor in (self.gerente, self.admin):
            with self.subTest(actor.username):
                self.assertEqual(self.post(actor, self.j2, "1").status_code, 302)
                self.assertTrue(Usuario.objects.get(pk=self.j2.pk).de_guardia)
                self.post(actor, self.j2, "0")
                self.assertFalse(Usuario.objects.get(pk=self.j2.pk).de_guardia)

    def test_senior_y_junior_no_pueden(self):
        self.assertEqual(self.post(self.s1, self.j2, "1").status_code, 403)
        self.assertEqual(self.post(self.j1, self.j2, "1").status_code, 403)
        self.assertFalse(Usuario.objects.get(pk=self.j2.pk).de_guardia)

    def test_no_se_marca_a_una_persona_inactiva(self):
        Usuario.objects.filter(pk=self.j2.pk).update(is_active=False)
        self.post(self.gerente, self.j2, "1")
        self.assertFalse(Usuario.objects.get(pk=self.j2.pk).de_guardia)

    def test_la_pestana_muestra_la_columna_y_la_marca(self):
        self.client.force_login(self.gerente)
        r = self.client.get(reverse("personal"))
        self.assertContains(r, "De guardia")
        self.assertContains(r, "Quitar guardia")  # la persona de guardia del fixture
        self.assertContains(r, "Marcar de guardia")

    def test_la_guardia_marcada_recibe_la_alerta(self):
        self.post(self.gerente, self.j2, "1")
        alerta = self.activar()
        self.assertIn(self.j2, alerta.destinatarios.all())
