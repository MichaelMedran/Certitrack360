"""Reglas de negocio del SDD §10: verificación, historial, observaciones y Poka-Yoke con campos de opción."""
import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.alertas.models import Notificacion
from apps.clientes.models import PlantillaTDR
from apps.entregables import adjuntos, servicios
from apps.entregables.models import Entregable, Observacion
from apps.entregables.tests import Base
from django.core.files.uploadedfile import SimpleUploadedFile

E = Entregable.Estado


class DatosObligatoriosParaVerificarTests(Base):
    """Transición EN_PROCESO → VERIFICACION_SENIOR: «datos obligatorios completos» (SDD §10.1)."""

    def en_proceso(self, datos):
        e = self.nuevo(self.c1, self.j1, self.s1, "Con datos", estado=E.EN_PROCESO)
        e.datos = datos
        e.save()
        return e

    def test_con_los_datos_completos_pasa(self):
        e = self.en_proceso({"c_periodo": "Enero", "c_nivel": "3"})
        servicios.mover(e, E.VERIFICACION_SENIOR, self.j1)
        self.assertEqual(e.estado, E.VERIFICACION_SENIOR)

    def test_faltan_datos_y_el_mensaje_los_nombra(self):
        e = self.en_proceso({"c_periodo": "Enero", "c_nivel": "  "})
        with self.assertRaises(ValidationError) as ctx:
            servicios.mover(e, E.VERIFICACION_SENIOR, self.j1)
        mensaje = ctx.exception.messages[0]
        self.assertIn("datos obligatorios («Nivel»)", mensaje)
        self.assertNotIn("«Periodo»", mensaje)
        self.assertIn("gerente o admin", mensaje)
        e.refresh_from_db()
        self.assertEqual(e.estado, E.EN_PROCESO)

    def test_un_cero_es_un_dato_valido(self):
        e = self.en_proceso({"c_periodo": "Enero", "c_nivel": "0"})
        servicios.mover(e, E.VERIFICACION_SENIOR, self.j1)
        self.assertEqual(e.estado, E.VERIFICACION_SENIOR)

    def test_datos_y_adjuntos_faltantes_se_informan_juntos(self):
        PlantillaTDR.objects.filter(pk=self.plantilla.pk).update(adjuntos_requeridos=["BORRADOR"])
        e = Entregable.objects.get(pk=self.en_proceso({}).pk)  # recargado: trae la plantilla actualizada
        with self.assertRaises(ValidationError) as ctx:
            servicios.mover(e, E.VERIFICACION_SENIOR, self.j1)
        mensaje = ctx.exception.messages[0]
        self.assertIn("los datos obligatorios («Periodo», «Nivel») y los adjuntos requeridos («Borrador»)", mensaje)

    def test_solo_se_exige_para_ir_a_verificacion(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Sin datos", estado=E.A_REALIZAR)
        e.datos = {}
        e.save()
        servicios.mover(e, E.EN_PROCESO, self.j1)  # empezar a trabajar no exige los datos completos
        self.assertEqual(e.estado, E.EN_PROCESO)

    def test_aplica_al_tablero(self):
        e = self.en_proceso({})
        self.client.force_login(self.j1)
        r = self.client.post(reverse("tablero_mover", args=[e.pk]), {"estado": "VERIFICACION_SENIOR"},
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("«Periodo»", r.json()["error"])


class HistorialTests(Base):
    def test_cada_transicion_valida_queda_registrada_con_usuario_y_fecha(self):
        servicios.mover(self.e1, E.EN_PROCESO, self.j1)
        servicios.mover(self.e1, E.VERIFICACION_SENIOR, self.j1)
        servicios.mover(self.e1, E.LISTO_PARA_ENTREGA, self.s1)
        filas = list(self.e1.historial.order_by("id"))
        self.assertEqual([(h.estado_anterior, h.estado_nuevo, h.usuario) for h in filas], [
            (E.A_REALIZAR, E.EN_PROCESO, self.j1),
            (E.EN_PROCESO, E.VERIFICACION_SENIOR, self.j1),
            (E.VERIFICACION_SENIOR, E.LISTO_PARA_ENTREGA, self.s1),
        ])
        self.assertTrue(all(h.fecha for h in filas))

    def test_una_transicion_rechazada_no_deja_rastro(self):
        with self.assertRaises(ValidationError):
            servicios.mover(self.e1, E.HECHO, self.s1)
        self.assertEqual(self.e1.historial.count(), 0)

    def test_devolver_deja_el_motivo_en_el_historial(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "V", estado=E.VERIFICACION_SENIOR)
        servicios.mover(e, E.EN_PROCESO, self.s1, tipo_error="FORMATO", descripcion="Falta numeración")
        h = e.historial.get()
        self.assertEqual(h.descripcion, "Estado: Verificación senior → En proceso (Devuelto con observación (Formato))")

    def test_devolver_sin_observacion_falla(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "V", estado=E.VERIFICACION_SENIOR)
        for kwargs in ({}, {"tipo_error": "FORMATO"}, {"descripcion": "algo"}, {"tipo_error": "MALO", "descripcion": "x"}):
            with self.subTest(**kwargs), self.assertRaises(ValidationError):
                servicios.mover(e, E.EN_PROCESO, self.s1, **kwargs)
        e.refresh_from_db()
        self.assertEqual(e.estado, E.VERIFICACION_SENIOR)
        self.assertEqual(e.historial.count(), 0)
        self.assertEqual(e.observaciones.count(), 0)

    def test_la_creacion_queda_en_el_historial_y_avisa_al_junior(self):
        self.client.force_login(self.s1)
        r = self.client.post(reverse("entregable_nuevo"), {
            "plantilla": self.plantilla.pk, "contrato": self.c1.pk, "titulo": "Nuevo", "junior_asignado": self.j1.pk,
            "plazo": (self.hoy + datetime.timedelta(days=4)).isoformat(), "c_periodo": "Enero", "c_nivel": "2"})
        self.assertEqual(r.status_code, 302)
        e = Entregable.objects.get(titulo="Nuevo")
        h = e.historial.get()
        self.assertEqual((h.estado_anterior, h.estado_nuevo, h.usuario), ("", E.A_REALIZAR, self.s1))
        self.assertEqual(h.descripcion, "Estado: — → A realizar (Entregable creado)")
        self.assertTrue(Notificacion.objects.filter(usuario=self.j1, entregable=e, tipo="ASIGNACION").exists())


class ObservacionesTests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.obs = Observacion.objects.create(entregable=cls.e1, autor=cls.s1, tipo_error="FORMATO", descripcion="Ajustar títulos")

    def resolver(self, usuario, solucion="Se corrigió"):
        self.client.force_login(usuario)
        return self.client.post(reverse("observacion_resolver", args=[self.obs.pk]), {"solucion": solucion})

    def test_la_ruta_es_la_del_sdd(self):
        self.assertEqual(reverse("observacion_resolver", args=[7]), "/observaciones/7/resolver/")
        self.assertEqual(reverse("entregable_estado", args=[7]), "/entregables/7/mover/")

    def test_el_senior_la_resuelve_con_su_solucion(self):
        self.assertEqual(self.resolver(self.s1).status_code, 302)
        self.obs.refresh_from_db()
        self.assertTrue(self.obs.resuelta)
        self.assertEqual(self.obs.solucion, "Se corrigió")

    def test_no_se_resuelve_sin_solucion(self):
        self.resolver(self.s1, solucion="   ")
        self.obs.refresh_from_db()
        self.assertFalse(self.obs.resuelta)

    def test_el_junior_no_puede_resolver(self):
        self.assertEqual(self.resolver(self.j1).status_code, 403)
        self.obs.refresh_from_db()
        self.assertFalse(self.obs.resuelta)

    def test_quien_no_ve_el_entregable_recibe_404(self):
        for usuario in (self.j2, self.s2):
            self.assertEqual(self.resolver(usuario).status_code, 404)

    def test_registrar_observacion_avisa_al_junior(self):
        self.client.force_login(self.s1)
        r = self.client.post(reverse("observacion_nueva", args=[self.e1.pk]),
                             {"tipo_error": "CONTENIDO", "descripcion": "Falta un anexo"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Notificacion.objects.filter(usuario=self.j1, tipo="OBSERVACION").exists())

    def test_el_junior_no_registra_observaciones(self):
        self.client.force_login(self.j1)
        r = self.client.post(reverse("observacion_nueva", args=[self.e1.pk]), {"tipo_error": "FORMATO", "descripcion": "x"})
        self.assertEqual(r.status_code, 403)


class CamposDeOpcionTests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.con_opcion = PlantillaTDR.objects.create(nombre="Con opción", campos_requeridos=[
            {"nombre": "c_nivel", "etiqueta": "Nivel", "tipo": "opcion", "opciones": ["Alto", "Bajo"]}])

    def crear(self, **extra):
        self.client.force_login(self.s1)
        datos = {"plantilla": self.con_opcion.pk, "contrato": self.c1.pk, "titulo": "Con opción",
                 "junior_asignado": self.j1.pk, "plazo": (self.hoy + datetime.timedelta(days=3)).isoformat()}
        datos.update(extra)
        return self.client.post(reverse("entregable_nuevo"), datos)

    def test_el_formulario_ofrece_las_opciones(self):
        self.client.force_login(self.s1)
        r = self.client.get(reverse("entregable_nuevo"), {"plantilla": self.con_opcion.pk})
        self.assertContains(r, "<option value=\"Alto\">Alto</option>", html=True)
        self.assertContains(r, "<option value=\"Bajo\">Bajo</option>", html=True)

    def test_una_opcion_valida_se_guarda(self):
        self.assertEqual(self.crear(c_nivel="Alto").status_code, 302)
        self.assertEqual(Entregable.objects.get(titulo="Con opción").datos, {"c_nivel": "Alto"})

    def test_una_opcion_inventada_se_rechaza(self):
        r = self.crear(c_nivel="Medio")
        self.assertContains(r, "Elija una opción válida para «Nivel».")
        self.assertFalse(Entregable.objects.filter(titulo="Con opción").exists())

    def test_sin_elegir_dice_que_falta(self):
        self.assertContains(self.crear(c_nivel=""), "Falta completar el campo «Nivel».")


class ContratosDadosDeBajaTests(Base):
    """Baja lógica (SDD §9.3): el historial se conserva pero no se crean entregables nuevos."""

    def datos(self, contrato):
        return {"plantilla": self.plantilla.pk, "contrato": contrato.pk, "titulo": "Nuevo", "junior_asignado": self.j1.pk,
                "plazo": (self.hoy + datetime.timedelta(days=3)).isoformat(), "c_periodo": "Enero", "c_nivel": "1"}

    def test_un_contrato_vigente_admite_entregables(self):
        self.client.force_login(self.s1)
        self.assertEqual(self.client.post(reverse("entregable_nuevo"), self.datos(self.c1)).status_code, 302)

    def test_un_contrato_dado_de_baja_no_admite_entregables_nuevos(self):
        self.c1.activo = False
        self.c1.save()
        self.client.force_login(self.s1)
        r = self.client.post(reverse("entregable_nuevo"), self.datos(self.c1))
        self.assertContains(r, "Elija un contrato vigente")
        self.assertFalse(Entregable.objects.filter(titulo="Nuevo").exists())

    def test_un_cliente_dado_de_baja_tampoco(self):
        self.cliente.activo = False
        self.cliente.save()
        self.client.force_login(self.gerente)
        r = self.client.post(reverse("entregable_nuevo"), self.datos(self.c1))
        self.assertContains(r, "Elija un contrato vigente")

    def test_el_historial_sigue_visible_tras_la_baja(self):
        self.c1.activo = False
        self.c1.save()
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).status_code, 200)
        titulos = [e.titulo for e in self.client.get(reverse("entregables")).context["entregables"]]
        self.assertEqual(titulos, ["E1"])

    def test_el_aviso_de_que_no_hay_contratos_para_un_senior_sin_contratos_vigentes(self):
        self.c1.activo = False
        self.c1.save()
        self.client.force_login(self.s1)
        self.assertFalse(self.client.get(reverse("entregable_nuevo")).context["hay_contratos"])

    def test_se_da_de_baja_desde_el_formulario_de_gestion(self):
        self.client.force_login(self.gerente)
        url = reverse("adm_editar", args=["contratos", self.c1.pk])
        datos = {"cliente": self.cliente.pk, "numero_contrato": "C1", "descripcion": "", "fecha_inicio": "2026-01-01",
                 "fecha_fin": "2027-01-01", "senior_responsable": self.s1.pk, "juniors": [self.j1.pk]}
        self.assertEqual(self.client.post(url, datos).status_code, 302)  # sin «activo»: queda dado de baja
        self.c1.refresh_from_db()
        self.assertFalse(self.c1.activo)
        self.assertContains(self.client.get(reverse("adm_lista", args=["contratos"])), "<td>No</td>", html=True)

    def test_un_contrato_existente_conserva_su_cliente_aunque_este_dado_de_baja(self):
        self.cliente.activo = False
        self.cliente.save()
        self.client.force_login(self.gerente)
        r = self.client.get(reverse("adm_editar", args=["contratos", self.c1.pk]))
        self.assertIn(self.cliente, r.context["form"].fields["cliente"].queryset)


class AdjuntosYDatosEnElFlujoCompletoTests(Base):
    """Flujo de punta a punta: crear, adjuntar, enviar a verificación, aprobar y cerrar."""

    def test_flujo_completo(self):
        PlantillaTDR.objects.filter(pk=self.plantilla.pk).update(adjuntos_requeridos=["BORRADOR"])
        e = Entregable.objects.get(pk=self.nuevo(self.c1, self.j1, self.s1, "Flujo", estado=E.A_REALIZAR).pk)
        servicios.mover(e, E.EN_PROCESO, self.j1)
        with self.assertRaises(ValidationError):
            servicios.mover(e, E.VERIFICACION_SENIOR, self.j1)
        adjuntos.subir(e, self.j1, SimpleUploadedFile("borrador.pdf", b"%PDF"), "BORRADOR")
        servicios.mover(e, E.VERIFICACION_SENIOR, self.j1)
        with self.assertRaises(PermissionDenied):
            servicios.mover(e, E.LISTO_PARA_ENTREGA, self.j1)  # el junior no aprueba
        servicios.mover(e, E.LISTO_PARA_ENTREGA, self.s1)
        servicios.mover(e, E.HECHO, self.gerente)
        self.assertEqual(e.historial.filter(estado_anterior__in=E.values).count(), 5)  # 4 transiciones + 1 subida
        self.assertEqual(e.historial.exclude(detalle="").count(), 1)
