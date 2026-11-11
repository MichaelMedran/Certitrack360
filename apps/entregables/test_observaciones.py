"""SDD del Sprint 2, hito S2-H3: observaciones y revisiones (RF-25, RF-26, RF-27 y el aviso inmediato de RF-22).

Casos clave de la §13: 17 (observar en revisión devuelve a En proceso, muestra «Con correcciones pendientes» y avisa al
junior) y 18 (no se resuelve una observación sin acción correctiva; no se aprueba con observaciones abiertas).
"""
import importlib
import re

from django.apps import apps as registro
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.alertas.models import Notificacion
from apps.conocimiento.models import LeccionAprendida
from apps.entregables import adjuntos, filtros, servicios, subestado
from apps.entregables import observaciones as obs_servicio
from apps.entregables.models import Entregable, HistorialEstado, Observacion
from apps.entregables.testing import aprobar, entregar
from apps.entregables.tests import Base
from apps.entregables.visibilidad import entregables_visibles

E = Entregable.Estado
O = Observacion.Estado
ETIQUETA = "Con correcciones pendientes"


class ObsBase(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.proc = cls.nuevo(cls.c1, cls.j1, cls.s1, "En proceso", E.EN_PROCESO)
        cls.obs = Observacion.objects.create(entregable=cls.proc, autor=cls.s1, tipo_error="FORMATO",
                                             descripcion="Títulos fuera de estilo")

    def refrescar(self, *objetos):
        for o in objetos:
            o.refresh_from_db()

    def post(self, usuario, nombre, args, datos=None, **extra):
        self.client.force_login(usuario)
        return self.client.post(reverse(nombre, args=args), datos or {}, **extra)


# ------------------------------------------------------------------ modelo y migración

class ModeloTests(ObsBase):
    def test_estado_por_defecto_y_responsable_el_junior_asignado(self):
        self.assertEqual((self.obs.estado, self.obs.resuelta, self.obs.responsable), (O.PENDIENTE, False, self.j1))

    def test_resuelta_true_del_sprint_1_queda_resuelta(self):
        o = Observacion.objects.create(entregable=self.proc, autor=self.s1, tipo_error="PLAZO", descripcion="x",
                                       solucion="ok", resuelta=True)
        self.assertEqual(o.estado, O.RESUELTA)
        self.assertEqual(Observacion.objects.get(pk=o.pk).estado, O.RESUELTA)

    def test_resuelta_y_estado_se_sincronizan_en_save(self):
        o = Observacion.objects.get(pk=self.obs.pk)
        o.estado = O.RESUELTA
        o.save()
        self.assertTrue(Observacion.objects.get(pk=o.pk).resuelta)
        o = Observacion.objects.get(pk=o.pk)
        o.resuelta = False  # como lo haría código del Sprint 1
        o.save(update_fields=["resuelta"])  # update_fields incluye también el estado
        self.assertEqual(Observacion.objects.filter(pk=o.pk).values_list("estado", "resuelta").get(), (O.PENDIENTE, False))
        o = Observacion.objects.get(pk=o.pk)
        o.estado = O.EN_CORRECCION
        o.save()
        self.assertFalse(Observacion.objects.get(pk=o.pk).resuelta)

    def test_la_accion_correctiva_es_la_solucion(self):
        self.obs.solucion = "Se corrigió"
        self.assertEqual(self.obs.accion_correctiva, "Se corrigió")
        self.assertNotIn("accion_correctiva", [f.name for f in Observacion._meta.get_fields()])

    def test_los_querysets_abiertas_y_pendientes(self):
        corr = Observacion.objects.create(entregable=self.proc, autor=self.s1, tipo_error="PLAZO", descripcion="y",
                                          estado=O.EN_CORRECCION, solucion="z")
        Observacion.objects.create(entregable=self.proc, autor=self.s1, tipo_error="OTRO", descripcion="w",
                                   solucion="v", resuelta=True)
        self.assertEqual(set(self.proc.observaciones.abiertas()), {self.obs, corr})
        self.assertEqual(set(self.proc.observaciones.pendientes()), {self.obs})


class MigracionTests(ObsBase):
    migracion = importlib.import_module("apps.entregables.migrations.0004_estados_de_observacion")

    def test_rellena_estado_desde_resuelta_y_responsable_con_el_junior(self):
        resuelta = Observacion.objects.create(entregable=self.e2, autor=self.s2, tipo_error="PLAZO", descripcion="x",
                                              solucion="ok", resuelta=True)
        # Como estaban antes del Sprint 2: sin responsable y con el estado por defecto.
        Observacion.objects.update(responsable=None, estado=O.PENDIENTE)
        self.migracion.rellenar(registro, None)
        self.assertEqual(Observacion.objects.filter(pk=resuelta.pk).values_list("estado", "responsable").get(),
                         (O.RESUELTA, self.j2.pk))
        self.assertEqual(Observacion.objects.filter(pk=self.obs.pk).values_list("estado", "responsable").get(),
                         (O.PENDIENTE, self.j1.pk))

    def test_es_aditiva_y_tiene_reversa(self):
        tipos = {type(op).__name__ for op in self.migracion.Migration.operations}
        self.assertEqual(tipos, {"AddField", "RunPython"})
        runpython = [op for op in self.migracion.Migration.operations if type(op).__name__ == "RunPython"][0]
        self.assertTrue(runpython.reversible)


# ------------------------------------------------------------------ condiciones nuevas de servicios.mover (§7.1)

class CondicionesDeMoverTests(ObsBase):
    def test_no_pasa_a_revision_con_observaciones_pendientes_y_dice_cuales(self):
        with self.assertRaises(ValidationError) as ctx:
            servicios.mover(self.proc, E.VERIFICACION_SENIOR, self.j1)
        self.assertEqual(ctx.exception.messages, [
            "No se puede enviar a revisión: hay 1 observación pendiente («Formato»). "
            "Registre la acción correctiva en la sección Observaciones."])
        self.refrescar(self.proc)
        self.assertEqual(self.proc.estado, E.EN_PROCESO)
        self.assertFalse(self.proc.historial.exists())

    def test_con_la_correccion_registrada_si_pasa_a_revision(self):
        obs_servicio.corregir(self.obs, self.j1, "Títulos corregidos")
        servicios.mover(self.proc, E.VERIFICACION_SENIOR, self.j1)
        self.assertEqual(self.proc.estado, E.VERIFICACION_SENIOR)

    def test_no_se_aprueba_con_observaciones_abiertas(self):
        obs_servicio.corregir(self.obs, self.j1, "Títulos corregidos")
        servicios.mover(self.proc, E.VERIFICACION_SENIOR, self.j1)
        with self.assertRaises(ValidationError) as ctx:
            servicios.mover(self.proc, E.LISTO_PARA_ENTREGA, self.s1)
        self.assertIn("No se puede aprobar: hay 1 observación abierta («Formato» en corrección)", ctx.exception.messages[0])
        Observacion.objects.create(entregable=self.proc, autor=self.s1, tipo_error="PLAZO", descripcion="otra")
        with self.assertRaises(ValidationError) as ctx:
            servicios.mover(self.proc, E.LISTO_PARA_ENTREGA, self.gerente)
        self.assertIn("2 observaciones abiertas", ctx.exception.messages[0])
        self.assertIn("«Plazo» pendiente", ctx.exception.messages[0])

    def test_con_todas_resueltas_se_aprueba(self):
        obs_servicio.corregir(self.obs, self.j1, "Títulos corregidos")
        servicios.mover(self.proc, E.VERIFICACION_SENIOR, self.j1)
        obs_servicio.confirmar(self.obs, self.s1)
        aprobar(self.proc, self.s1)  # Sprint 3 (RF-45): con la revisión de calidad conforme
        self.assertEqual(self.proc.estado, E.LISTO_PARA_ENTREGA)

    def test_los_motivos_de_datos_y_de_observaciones_se_dicen_juntos(self):
        self.proc.datos = {}
        self.proc.save()
        with self.assertRaises(ValidationError) as ctx:
            servicios.mover(self.proc, E.VERIFICACION_SENIOR, self.j1)
        self.assertEqual(len(ctx.exception.messages), 2)
        self.assertIn("los datos obligatorios", ctx.exception.messages[0])
        self.assertIn("observación pendiente", ctx.exception.messages[1])

    def test_por_el_tablero_responde_422_con_el_motivo(self):
        r = self.post(self.j1, "entregable_estado", [self.proc.pk], {"estado": "VERIFICACION_SENIOR"}, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 422)
        self.assertContains(r, "hay 1 observación pendiente", status_code=422)
        self.assertNotIn("HX-Trigger", r)  # no es el diálogo de devolución

    def test_la_devolucion_del_sprint_1_sigue_igual_y_no_duplica(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "V", E.VERIFICACION_SENIOR)
        servicios.mover(e, E.EN_PROCESO, self.s1, tipo_error="FORMATO", descripcion="Falta numeración")
        o = e.observaciones.get()
        self.assertEqual((o.estado, o.responsable, o.autor), (O.PENDIENTE, self.j1, self.s1))
        aviso = Notificacion.objects.get(entregable=e, tipo="OBSERVACION")
        self.assertEqual(aviso.mensaje, f"{e.codigo} «V» fue devuelto con una observación.")
        self.assertEqual(aviso.destino, reverse("entregable_detalle", args=[e.pk]) + "#observaciones")


# ------------------------------------------------------------------ registrar (RF-26, caso 17)

class RegistrarTests(ObsBase):
    def filas(self, *filas):
        datos = {"tipo_error": [], "descripcion": [], "responsable": []}
        for tipo, descripcion, responsable in filas:
            datos["tipo_error"].append(tipo)
            datos["descripcion"].append(descripcion)
            datos["responsable"].append(responsable)
        return datos

    def test_caso_17_observar_en_revision_devuelve_marca_el_subestado_y_avisa_al_junior(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Informe técnico 03", E.VERIFICACION_SENIOR)
        r = self.post(self.s1, "observacion_nueva", [e.pk], self.filas(
            ("FORMATO", "Títulos del capítulo 2", self.j1.pk), ("CONTENIDO", "Total del cuadro 3", self.s1.pk)))
        self.assertRedirects(r, reverse("entregable_detalle", args=[e.pk]) + "#observaciones",
                             fetch_redirect_response=False)
        self.refrescar(e)
        self.assertEqual(e.estado, E.EN_PROCESO)
        # Las dos observaciones, una sola vez cada una, con su responsable.
        self.assertEqual(sorted(e.observaciones.values_list("tipo_error", "responsable", "estado")),
                         [("CONTENIDO", self.s1.pk, O.PENDIENTE), ("FORMATO", self.j1.pk, O.PENDIENTE)])
        cambio = e.historial.get(estado_anterior=E.VERIFICACION_SENIOR)
        self.assertEqual((cambio.estado_nuevo, cambio.usuario, cambio.detalle),
                         (E.EN_PROCESO, self.s1, "Devuelto con 2 observaciones (Formato, Contenido)"))
        aviso = Notificacion.objects.get(usuario=self.j1, entregable=e, tipo="OBSERVACION")
        self.assertEqual(aviso.mensaje, f"{e.codigo} «Informe técnico 03» fue devuelto con 2 observaciones.")
        self.assertIn(e.codigo, aviso.mensaje)
        # El subestado se ve en el detalle, el tablero, la lista y el calendario.
        self.client.force_login(self.j1)
        detalle = self.client.get(reverse("entregable_detalle", args=[e.pk]))
        self.assertContains(detalle, f'<span class="etiqueta subestado">{ETIQUETA}</span>')
        self.assertContains(self.client.get(reverse("tablero")), ETIQUETA)
        self.assertContains(self.client.get(reverse("entregables")), f"{E.EN_PROCESO.label} · <span")
        titulo = next(ev["title"] for ev in self.client.get(reverse("calendario_eventos")).json() if ev["id"] == e.pk)
        self.assertTrue(titulo.startswith(f"[{E.EN_PROCESO.label} · {ETIQUETA}] {e.codigo}"))

    def test_una_sola_en_revision_usa_los_textos_del_sprint_1(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "V", E.VERIFICACION_SENIOR)
        self.post(self.gerente, "observacion_nueva", [e.pk], {"tipo_error": "PLAZO", "descripcion": "Fecha errada"})
        self.refrescar(e)
        self.assertEqual(e.estado, E.EN_PROCESO)
        self.assertEqual(e.historial.get().detalle, "Devuelto con observación (Plazo)")
        self.assertEqual(Notificacion.objects.get(entregable=e, tipo="OBSERVACION").mensaje,
                         f"{e.codigo} «V» fue devuelto con una observación.")

    def test_fuera_de_revision_no_cambia_el_estado_y_avisa_con_el_codigo(self):
        self.post(self.s1, "observacion_nueva", [self.e1.pk], self.filas(
            ("FORMATO", "uno", ""), ("PLAZO", "dos", ""), ("", "  ", "")))  # la fila vacía se ignora
        self.refrescar(self.e1)
        self.assertEqual(self.e1.estado, E.A_REALIZAR)
        self.assertEqual(self.e1.observaciones.count(), 2)
        self.assertEqual(set(self.e1.observaciones.values_list("responsable", flat=True)), {self.j1.pk})
        aviso = Notificacion.objects.get(entregable=self.e1, tipo="OBSERVACION")
        self.assertEqual(aviso.mensaje, f"2 observaciones nuevas en {self.e1.codigo} «E1».")
        self.assertEqual(self.e1.historial.get().detalle, "Registró 2 observaciones (Formato, Plazo)")

    def test_una_fila_incompleta_rechaza_todo_el_envio(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "V", E.VERIFICACION_SENIOR)
        self.post(self.s1, "observacion_nueva", [e.pk], self.filas(("FORMATO", "bien", ""), ("PLAZO", "   ", "")))
        self.refrescar(e)
        self.assertEqual(e.estado, E.VERIFICACION_SENIOR)
        self.assertFalse(e.observaciones.exists())
        self.assertFalse(Notificacion.objects.filter(entregable=e).exists())
        self.client.force_login(self.s1)
        self.assertContains(self.client.get(reverse("entregable_detalle", args=[e.pk])), "Observación 2: Describa la observación.")

    def test_el_responsable_debe_ser_del_entregable(self):
        for valor in (self.j2.pk, self.s2.pk, "abc", "99999999999999999999999"):
            with self.subTest(valor=valor):
                self.post(self.s1, "observacion_nueva", [self.e1.pk], self.filas(("FORMATO", "x", valor)))
                self.assertFalse(self.e1.observaciones.exists())
        with self.assertRaises(ValidationError):
            obs_servicio.registrar(self.e1, self.s1, [{"tipo_error": "FORMATO", "descripcion": "x", "responsable": self.j2}])

    def test_permisos_de_registrar_con_los_cuatro_roles_y_ajenos(self):
        datos = {"tipo_error": "FORMATO", "descripcion": "x"}
        self.assertEqual(self.post(self.j1, "observacion_nueva", [self.e1.pk], datos).status_code, 403)
        self.assertEqual(self.post(self.j2, "observacion_nueva", [self.e1.pk], datos).status_code, 404)
        self.assertEqual(self.post(self.s2, "observacion_nueva", [self.e1.pk], datos).status_code, 404)
        for usuario in (self.s1, self.gerente, self.admin):
            self.assertEqual(self.post(usuario, "observacion_nueva", [self.e1.pk], datos).status_code, 302)
        self.assertEqual(self.e1.observaciones.count(), 3)
        with self.assertRaises(PermissionDenied):
            obs_servicio.registrar(self.e1, self.j1, [datos])

    def test_el_formulario_permite_varias_y_ofrece_los_responsables(self):
        self.client.force_login(self.s1)
        html = self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).content.decode()
        self.assertIn("Registrar observaciones", html)
        self.assertIn("+ Otra observación", html)
        self.assertIn("Registrar y avisar al junior", html)
        self.assertIn(f'<option value="{self.j1.pk}" selected>', html)
        self.assertNotIn(f'<option value="{self.j2.pk}"', html)
        self.client.force_login(self.j1)
        self.assertNotContains(self.client.get(reverse("entregable_detalle", args=[self.e1.pk])), "Registrar observaciones")


# ------------------------------------------------------------------ corregir y revisar (RF-25, caso 18)

class CorregirTests(ObsBase):
    def corregir(self, usuario, **datos):
        return self.post(usuario, "observacion_corregir", [self.obs.pk], {"accion_correctiva": "Títulos corregidos", **datos})

    def test_el_responsable_registra_la_correccion_con_evidencia_y_avisa_al_senior(self):
        a = adjuntos.subir(self.proc, self.j1, SimpleUploadedFile("informe.pdf", b"%PDF"), "BORRADOR")
        r = self.corregir(self.j1, evidencia=a.pk)
        self.assertEqual(r.status_code, 302)
        self.refrescar(self.obs)
        self.assertEqual((self.obs.estado, self.obs.solucion, self.obs.evidencia, self.obs.corregida_por),
                         (O.EN_CORRECCION, "Títulos corregidos", a, self.j1))
        self.assertIsNotNone(self.obs.corregida_en)
        self.assertFalse(self.obs.resuelta)
        aviso = Notificacion.objects.get(usuario=self.s1, tipo="CORRECCION")
        self.assertIn(self.proc.codigo, aviso.mensaje)
        self.assertEqual(aviso.entregable, self.proc)
        self.assertTrue(self.proc.historial.filter(detalle="Registró la corrección de una observación (Formato)").exists())

    def test_exige_texto(self):
        self.corregir(self.j1, accion_correctiva="   ")
        self.refrescar(self.obs)
        self.assertEqual(self.obs.estado, O.PENDIENTE)
        with self.assertRaises(ValidationError):
            obs_servicio.corregir(self.obs, self.j1, "")

    def test_la_evidencia_debe_ser_del_mismo_entregable(self):
        ajeno = adjuntos.subir(self.e2, self.j2, SimpleUploadedFile("otro.pdf", b"%PDF"), "BORRADOR")
        for valor in (ajeno.pk, "x", "99999999999999999999999"):
            with self.subTest(valor=valor):
                self.corregir(self.j1, evidencia=valor)
                self.refrescar(self.obs)
                self.assertEqual(self.obs.estado, O.PENDIENTE)

    def test_permisos_con_los_cuatro_roles_y_ajenos(self):
        self.assertEqual(self.corregir(self.j2).status_code, 404)
        self.assertEqual(self.corregir(self.s2).status_code, 404)
        for usuario in (self.s1, self.gerente, self.admin):  # un senior del entregable también puede
            with self.subTest(usuario=usuario.username):
                Observacion.objects.filter(pk=self.obs.pk).update(estado=O.PENDIENTE)
                self.assertEqual(self.corregir(usuario).status_code, 302)
                self.refrescar(self.obs)
                self.assertEqual(self.obs.estado, O.EN_CORRECCION)
        # Si el responsable es un senior, el junior asignado no puede registrar la corrección (403: la ve, no puede).
        Observacion.objects.filter(pk=self.obs.pk).update(estado=O.PENDIENTE, responsable=self.s1)
        self.assertEqual(self.corregir(self.j1).status_code, 403)

    def test_solo_desde_pendiente(self):
        obs_servicio.corregir(self.obs, self.j1, "Hecho")
        with self.assertRaises(ValidationError):
            obs_servicio.corregir(self.obs, self.j1, "Otra vez")

    def test_solo_post(self):
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(reverse("observacion_corregir", args=[self.obs.pk])).status_code, 405)
        self.assertEqual(self.client.get(reverse("observacion_revisar", args=[self.obs.pk])).status_code, 405)

    def test_las_rutas_son_las_del_sdd(self):
        self.assertEqual(reverse("observaciones"), "/observaciones/")
        self.assertEqual(reverse("observacion_corregir", args=[7]), "/observaciones/7/corregir/")
        self.assertEqual(reverse("observacion_revisar", args=[7]), "/observaciones/7/revisar/")
        self.assertEqual(reverse("observacion_resolver", args=[7]), "/observaciones/7/resolver/")


class RevisarTests(ObsBase):
    def setUp(self):
        obs_servicio.corregir(self.obs, self.j1, "Títulos corregidos")

    def revisar(self, usuario, decision, **datos):
        return self.post(usuario, "observacion_revisar", [self.obs.pk], {"decision": decision, **datos})

    def test_el_senior_confirma_y_queda_quien_y_cuando(self):
        self.assertEqual(self.revisar(self.s1, "confirmar").status_code, 302)
        self.refrescar(self.obs)
        self.assertEqual((self.obs.estado, self.obs.resuelta, self.obs.revisada_por), (O.RESUELTA, True, self.s1))
        self.assertIsNotNone(self.obs.resuelta_en)

    def test_rechazar_vuelve_a_pendiente_y_avisa_al_responsable(self):
        self.revisar(self.s1, "rechazar", motivo="Faltan los títulos del anexo")
        self.refrescar(self.obs)
        self.assertEqual((self.obs.estado, self.obs.resuelta), (O.PENDIENTE, False))
        aviso = Notificacion.objects.filter(usuario=self.j1, tipo="OBSERVACION").latest("id")
        self.assertIn("Se rechazó la corrección", aviso.mensaje)
        self.assertIn(self.proc.codigo, aviso.mensaje)
        self.assertTrue(self.proc.historial.filter(detalle__endswith="Faltan los títulos del anexo").exists())
        # Vuelve a impedir el paso a revisión.
        with self.assertRaises(ValidationError):
            servicios.mover(self.proc, E.VERIFICACION_SENIOR, self.j1)

    def test_permisos_con_los_cuatro_roles_y_ajenos(self):
        self.assertEqual(self.revisar(self.j1, "confirmar").status_code, 403)
        self.assertEqual(self.revisar(self.j2, "confirmar").status_code, 404)
        self.assertEqual(self.revisar(self.s2, "confirmar").status_code, 404)
        self.refrescar(self.obs)
        self.assertEqual(self.obs.estado, O.EN_CORRECCION)
        for usuario in (self.gerente, self.admin, self.s1):
            with self.subTest(usuario=usuario.username):
                self.assertEqual(self.revisar(usuario, "rechazar").status_code, 302)
                obs_servicio.corregir(Observacion.objects.get(pk=self.obs.pk), self.j1, "De nuevo")

    def test_una_decision_desconocida_no_cambia_nada(self):
        self.revisar(self.s1, "aprobar")
        self.refrescar(self.obs)
        self.assertEqual(self.obs.estado, O.EN_CORRECCION)

    def test_caso_18_no_se_resuelve_sin_accion_correctiva(self):
        Observacion.objects.filter(pk=self.obs.pk).update(solucion="  ")
        self.revisar(self.s1, "confirmar")
        self.refrescar(self.obs)
        self.assertEqual(self.obs.estado, O.EN_CORRECCION)
        otra = Observacion.objects.create(entregable=self.proc, autor=self.s1, tipo_error="PLAZO", descripcion="x")
        self.post(self.s1, "observacion_resolver", [otra.pk], {"solucion": "   "})
        self.refrescar(otra)
        self.assertEqual(otra.estado, O.PENDIENTE)
        with self.assertRaises(ValidationError):
            obs_servicio.confirmar(Observacion.objects.get(pk=otra.pk), self.s1)  # pendiente: no se confirma

    def test_resolver_del_sprint_1_registra_al_revisor(self):
        otra = Observacion.objects.create(entregable=self.proc, autor=self.s1, tipo_error="PLAZO", descripcion="x")
        self.post(self.s1, "observacion_resolver", [otra.pk], {"solucion": "Fecha corregida"})
        self.refrescar(otra)
        self.assertEqual((otra.estado, otra.resuelta, otra.solucion, otra.revisada_por),
                         (O.RESUELTA, True, "Fecha corregida", self.s1))
        with self.assertRaises(ValidationError):
            obs_servicio.resolver(otra, self.s1, "Otra vez")

    def test_las_lecciones_salen_de_las_resueltas_al_cerrar(self):
        servicios.mover(self.proc, E.VERIFICACION_SENIOR, self.j1)
        obs_servicio.confirmar(self.obs, self.s1)
        aprobar(self.proc, self.s1)  # Sprint 3 (RF-45): con la revisión de calidad conforme
        entregar(self.proc, self.s1)
        leccion = LeccionAprendida.objects.get(observacion_origen=self.obs)
        self.assertEqual(leccion.solucion, "Títulos corregidos")


class CorreccionesDeLaRevisionTests(ObsBase):
    """Hallazgos de la revisión de S2-H1-H2-ajustes y S2-H3 (R1 a R3)."""

    def en_revision_con_correccion(self, responsable=None):
        e = self.nuevo(self.c1, self.j1, self.s1, "En revisión", E.VERIFICACION_SENIOR)
        o = Observacion.objects.create(entregable=e, autor=self.s1, tipo_error="CONTENIDO", descripcion="Cuadro 3",
                                       responsable=responsable or self.j1)
        obs_servicio.corregir(o, self.j1 if responsable is None else responsable, "Total corregido")
        return e, o

    def test_r1_rechazar_en_revision_devuelve_a_en_proceso(self):
        e, o = self.en_revision_con_correccion()
        r = self.post(self.s1, "observacion_revisar", [o.pk], {"decision": "rechazar", "motivo": "Sigue mal"})
        self.assertEqual(r.status_code, 302)
        self.refrescar(e, o)
        self.assertEqual((e.estado, o.estado, o.solucion), (E.EN_PROCESO, O.PENDIENTE, "Total corregido"))
        self.assertTrue(subestado.aplica(e))
        cambio = e.historial.get(estado_anterior=E.VERIFICACION_SENIOR, estado_nuevo=E.EN_PROCESO)
        self.assertEqual((cambio.usuario, cambio.detalle), (self.s1, "Devuelto por corrección rechazada (Contenido)"))
        self.assertEqual(e.observaciones.count(), 1)  # no se crea otra observación
        avisos = Notificacion.objects.filter(entregable=e, tipo="OBSERVACION")
        self.assertEqual(avisos.count(), 1)  # el responsable es el junior: un solo aviso
        self.assertIn("Se rechazó la corrección", avisos.get().mensaje)
        self.assertIn(f"El entregable volvió a «{E.EN_PROCESO.label}»", avisos.get().mensaje)
        self.client.force_login(self.s1)
        self.assertContains(self.client.get(reverse("entregable_detalle", args=[e.pk])),
                            f'<span class="etiqueta subestado">{ETIQUETA}</span>')

    def test_r1_si_el_responsable_es_un_senior_tambien_avisa_al_junior(self):
        e, o = self.en_revision_con_correccion(responsable=self.s1)
        _, devuelto = obs_servicio.rechazar(o, self.gerente)
        self.assertTrue(devuelto)
        self.assertEqual(set(Notificacion.objects.filter(entregable=e, tipo="OBSERVACION")
                             .values_list("usuario", flat=True)), {self.s1.pk, self.j1.pk})

    def test_r1_fuera_de_revision_no_cambia_el_estado(self):
        obs_servicio.corregir(self.obs, self.j1, "Títulos corregidos")
        _, devuelto = obs_servicio.rechazar(self.obs, self.s1)
        self.refrescar(self.proc)
        self.assertFalse(devuelto)
        self.assertEqual(self.proc.estado, E.EN_PROCESO)
        self.assertFalse(self.proc.historial.exclude(estado_nuevo=E.EN_PROCESO).exists())
        self.assertFalse(self.proc.historial.exclude(estado_anterior=E.EN_PROCESO).exists())

    def test_r1_mover_por_rechazo_exige_una_observacion_pendiente_del_entregable(self):
        e, o = self.en_revision_con_correccion()
        with self.assertRaises(ValidationError):
            servicios.mover(e, E.EN_PROCESO, self.s1, rechazo=o)  # sigue En corrección
        with self.assertRaises(ValidationError):
            servicios.mover(e, E.EN_PROCESO, self.s1, rechazo=self.obs)  # de otro entregable
        self.refrescar(e)
        self.assertEqual(e.estado, E.VERIFICACION_SENIOR)

    def test_r2_resolver_no_sobrescribe_una_correccion_registrada(self):
        obs_servicio.corregir(self.obs, self.j1, "Texto del junior")
        r = self.post(self.s1, "observacion_resolver", [self.obs.pk], {"solucion": "Texto del senior"})
        self.assertEqual(r.status_code, 302)
        self.refrescar(self.obs)
        self.assertEqual((self.obs.estado, self.obs.solucion, self.obs.corregida_por),
                         (O.EN_CORRECCION, "Texto del junior", self.j1))
        with self.assertRaises(ValidationError):
            obs_servicio.resolver(self.obs, self.gerente, "Otro texto")
        self.client.force_login(self.s1)
        self.assertContains(self.client.get(reverse("entregable_detalle", args=[self.proc.pk])),
                            "Confirme o rechace la corrección.")

    def test_r3_no_se_registran_observaciones_en_aprobado_ni_en_entregado(self):
        datos = {"tipo_error": "FORMATO", "descripcion": "Tarde"}
        for estado in (E.LISTO_PARA_ENTREGA, E.HECHO):
            with self.subTest(estado=estado):
                e = self.nuevo(self.c1, self.j1, self.s1, f"En {estado}", estado)
                r = self.post(self.s1, "observacion_nueva", [e.pk], datos)
                self.assertEqual(r.status_code, 302)
                self.refrescar(e)
                self.assertEqual(e.estado, estado)
                self.assertFalse(e.observaciones.exists())
                self.assertFalse(Notificacion.objects.filter(entregable=e).exists())
                with self.assertRaises(ValidationError):
                    obs_servicio.registrar(e, self.gerente, [datos])
                html = self.client.get(reverse("entregable_detalle", args=[e.pk])).content.decode()
                self.assertIn("No se registran observaciones en un entregable", html)
                self.assertNotIn(reverse("observacion_nueva", args=[e.pk]), html)
                self.assertIn("no se registran observaciones nuevas", html)
        # Sigue sin cambio el permiso: un junior recibe 403 antes que el motivo del estado.
        self.assertEqual(self.post(self.j1, "observacion_nueva", [e.pk], datos).status_code, 403)


class HtmxYCsrfTests(ObsBase):
    def test_desde_htmx_responde_con_hx_redirect_a_la_seccion(self):
        r = self.post(self.j1, "observacion_corregir", [self.obs.pk], {"accion_correctiva": "ok"}, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["HX-Redirect"], reverse("entregable_detalle", args=[self.proc.pk]) + "#observaciones")

    def test_sin_token_csrf_se_rechaza_y_con_la_cabecera_de_htmx_pasa(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.j1)
        url = reverse("observacion_corregir", args=[self.obs.pk])
        self.assertEqual(cliente.post(url, {"accion_correctiva": "ok"}).status_code, 403)
        self.refrescar(self.obs)
        self.assertEqual(self.obs.estado, O.PENDIENTE)
        html = cliente.get(reverse("entregable_detalle", args=[self.proc.pk])).content.decode()
        token = re.search(r'"X-CSRFToken": "([^"]+)"', html).group(1)  # hx-headers del <body>
        r = cliente.post(url, {"accion_correctiva": "ok"}, HTTP_HX_REQUEST="true", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 200)
        self.refrescar(self.obs)
        self.assertEqual(self.obs.estado, O.EN_CORRECCION)


# ------------------------------------------------------------------ detalle

class DetalleTests(ObsBase):
    def ver(self, usuario, e=None):
        self.client.force_login(usuario)
        return self.client.get(reverse("entregable_detalle", args=[(e or self.proc).pk]))

    def test_estados_en_texto_y_acciones_segun_el_rol(self):
        r = self.ver(self.j1)
        self.assertContains(r, '<span class="etiqueta obs-pendiente">Pendiente</span>')
        self.assertContains(r, "Responsable: j1")
        self.assertContains(r, reverse("observacion_corregir", args=[self.obs.pk]))
        self.assertNotContains(r, reverse("observacion_revisar", args=[self.obs.pk]))
        self.assertContains(r, ETIQUETA)
        self.assertContains(r, "No se puede enviar a revisión: hay 1 observación pendiente («Formato»)")
        obs_servicio.corregir(self.obs, self.j1, "Títulos corregidos")
        r = self.ver(self.s1)
        self.assertContains(r, '<span class="etiqueta obs-en_correccion">En corrección</span>')
        self.assertContains(r, "Confirmar corrección (resuelta)")
        self.assertContains(r, "Rechazar y volver a pendiente")
        self.assertContains(r, "Acción correctiva:</strong> Títulos corregidos")
        self.assertNotContains(self.ver(self.j1), reverse("observacion_revisar", args=[self.obs.pk]))

    def test_en_revision_avisa_lo_que_falta_para_aprobar(self):
        obs_servicio.corregir(self.obs, self.j1, "Títulos corregidos")
        servicios.mover(self.proc, E.VERIFICACION_SENIOR, self.j1)
        r = self.ver(self.s1)
        self.assertContains(r, "No se puede aprobar: hay 1 observación abierta")
        self.assertNotContains(r, f'<span class="etiqueta subestado">')  # en revisión no aplica el subestado

    def test_resuelta_muestra_quien_la_reviso(self):
        obs_servicio.corregir(self.obs, self.j1, "Títulos corregidos")
        obs_servicio.confirmar(self.obs, self.gerente)
        r = self.ver(self.j1)
        self.assertContains(r, '<span class="etiqueta obs-resuelta">Resuelta</span>')
        self.assertContains(r, "Revisada por ger el")
        self.assertNotContains(r, f'<span class="etiqueta subestado">')


# ------------------------------------------------------------------ subestado y filtro de estado

class SubestadoTests(ObsBase):
    def test_el_filtro_de_estado_ofrece_el_subestado_y_no_amplia_la_visibilidad(self):
        Observacion.objects.create(entregable=self.e2, autor=self.s2, tipo_error="FORMATO", descripcion="x")
        Entregable.objects.filter(pk=self.e2.pk).update(estado=E.EN_PROCESO)
        params = {"estado": subestado.VALOR}
        self.assertEqual(list(filtros.aplicar(entregables_visibles(self.j1), params).queryset), [self.proc])
        self.assertEqual(list(filtros.aplicar(entregables_visibles(self.j2), params).queryset), [self.e2])
        self.assertEqual(set(filtros.aplicar(entregables_visibles(self.gerente), params).queryset), {self.proc, self.e2})
        self.client.force_login(self.j1)
        r = self.client.get(reverse("entregables"), params)
        self.assertEqual([e.titulo for e in r.context["entregables"]], ["En proceso"])
        self.assertContains(r, f'<option value="{subestado.VALOR}" selected>{ETIQUETA}</option>')
        self.assertContains(r, f"Estado: {ETIQUETA}")  # chip
        ids = {ev["id"] for ev in self.client.get(reverse("calendario_eventos"), params).json()}
        self.assertEqual(ids, {self.proc.pk})

    def test_sin_observaciones_abiertas_o_fuera_de_en_proceso_no_aplica(self):
        obs_servicio.resolver(self.obs, self.s1, "listo")
        self.assertFalse(subestado.aplica(Entregable.objects.get(pk=self.proc.pk)))
        self.assertEqual(list(filtros.aplicar(entregables_visibles(self.s1), {"estado": subestado.VALOR}).queryset), [])
        e = self.nuevo(self.c1, self.j1, self.s1, "En revisión", E.VERIFICACION_SENIOR)
        Observacion.objects.create(entregable=e, autor=self.s1, tipo_error="FORMATO", descripcion="x",
                                   estado=O.EN_CORRECCION, solucion="y")
        self.assertFalse(subestado.aplica(e))

    def test_tarjetas_lista_y_calendario_sin_una_consulta_por_entregable(self):
        self.client.force_login(self.gerente)

        def consultas(nombre):
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 200)
            return len(ctx.captured_queries)

        antes = {n: consultas(n) for n in ("tablero", "entregables", "calendario_eventos")}
        for i in range(5):
            e = self.nuevo(self.c1, self.j1, self.s1, f"Más {i}", E.EN_PROCESO)
            Observacion.objects.create(entregable=e, autor=self.s1, tipo_error="FORMATO", descripcion="x")
        self.assertEqual({n: consultas(n) for n in antes}, antes)


# ------------------------------------------------------------------ historial de observaciones (RF-27)

class HistorialDeObservacionesTests(ObsBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.ajena = Observacion.objects.create(entregable=cls.e2, autor=cls.s2, tipo_error="PLAZO", descripcion="ajena")
        cls.resuelta = Observacion.objects.create(entregable=cls.e1, autor=cls.s1, tipo_error="CONTENIDO",
                                                  descripcion="resuelta", solucion="ok", resuelta=True)

    def ids(self, usuario, **params):
        self.client.force_login(usuario)
        r = self.client.get(reverse("observaciones"), params)
        self.assertEqual(r.status_code, 200)
        return {o.pk for o in r.context["observaciones"]}

    def test_cada_rol_ve_solo_las_de_sus_entregables(self):
        propias = {self.obs.pk, self.resuelta.pk}
        self.assertEqual(self.ids(self.j1), propias)
        self.assertEqual(self.ids(self.s1), propias)
        self.assertEqual(self.ids(self.j2), {self.ajena.pk})
        self.assertEqual(self.ids(self.s2), {self.ajena.pk})
        for usuario in (self.gerente, self.admin):
            self.assertEqual(self.ids(usuario), propias | {self.ajena.pk})

    def test_los_filtros_reducen_y_nunca_amplian(self):
        self.assertEqual(self.ids(self.gerente, estado="PENDIENTE"), {self.obs.pk, self.ajena.pk})
        self.assertEqual(self.ids(self.gerente, tipo_error="CONTENIDO"), {self.resuelta.pk})
        self.assertEqual(self.ids(self.gerente, contrato=self.c2.pk), {self.ajena.pk})
        self.assertEqual(self.ids(self.gerente, cliente=self.cliente.pk, responsable=self.j2.pk), {self.ajena.pk})
        self.assertEqual(self.ids(self.gerente, entregable=self.proc.codigo), {self.obs.pk})
        self.assertEqual(self.ids(self.gerente, entregable="en proc"), {self.obs.pk})
        # Un junior que pide lo ajeno no recibe nada.
        self.assertEqual(self.ids(self.j1, contrato=self.c2.pk), set())
        self.assertEqual(self.ids(self.j1, responsable=self.j2.pk), set())
        self.assertEqual(self.ids(self.j1, entregable=self.e2.codigo), set())
        # Valores no válidos se ignoran (sin error 500).
        self.assertEqual(self.ids(self.j1, cliente="x", contrato="99999999999999999999999", estado="MALO",
                                  tipo_error="?", responsable="²"), {self.obs.pk, self.resuelta.pk})

    def test_las_opciones_solo_muestran_lo_visible(self):
        self.client.force_login(self.j1)
        opciones = self.client.get(reverse("observaciones")).context["opciones"]
        self.assertEqual(set(opciones["contratos"]), {self.c1})
        self.assertEqual(set(opciones["responsables"]), {self.j1})

    def test_columnas_estado_en_texto_y_enlace_al_detalle(self):
        obs_servicio.corregir(self.obs, self.j1, "Títulos corregidos")
        self.client.force_login(self.j1)
        r = self.client.get(reverse("observaciones"))
        for columna in ("Fecha", "Entregable", "Cliente · contrato", "Tipo", "Descripción", "Responsable", "Estado", "Atendida"):
            self.assertContains(r, f"<th>{columna}</th>")
        self.assertContains(r, "En corrección")
        self.assertContains(r, reverse("entregable_detalle", args=[self.proc.pk]) + "#observaciones")
        self.assertContains(r, self.proc.codigo)

    def test_es_pestana_de_entregables_y_htmx_recibe_el_fragmento(self):
        self.client.force_login(self.j1)
        lista = self.client.get(reverse("entregables")).content.decode()
        pestanas = re.search(r'<nav class="pestanas" aria-label="Entregables">.*?</nav>', lista, flags=re.S).group(0)
        self.assertIn(f'href="{reverse("observaciones")}"', pestanas)
        r = self.client.get(reverse("observaciones"))
        self.assertContains(r, '<a href="/entregables/" aria-current="page">Entregables</a>')  # sección de la barra
        self.assertContains(r, 'aria-current="true">Observaciones</a>')
        parcial = self.client.get(reverse("observaciones"), {"estado": "PENDIENTE"}, HTTP_HX_REQUEST="true")
        self.assertNotContains(parcial, "<html")
        self.assertContains(parcial, 'hx-swap-oob="true"')

    def test_sin_sesion_redirige_al_ingreso(self):
        self.client.logout()
        r = self.client.get(reverse("observaciones"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("login"), r["Location"])
