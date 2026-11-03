"""Pruebas del plan de incorporación por rol (SDD del Sprint 2, §7.12, §8 y §13, RF-38: HU-15, Caso 28)."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.alertas.models import Notificacion
from apps.conocimiento.models import Procedimiento
from apps.cuentas.models import Usuario
from apps.entregables.testing import MediaTemporal
from apps.entregables.tests import Base
from apps.equipo import servicios
from apps.equipo.models import ActividadPlan, AvanceActividad, Incorporacion, PlanIncorporacion
from apps.repositorio import servicios as repo_srv
from apps.repositorio.models import DocumentoRepositorio


def _archivo(nombre="plantilla.docx", contenido=b"formato"):
    return SimpleUploadedFile(nombre, contenido, content_type="application/octet-stream")


class Caso28IncorporacionTests(Base):
    """Caso 28 (SDD §13): el ingresante ve pendientes y completadas; los enlaces apuntan siempre a la versión vigente;
    solo el responsable confirma el fin del plan de incorporación, y solo con todas las actividades completadas."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.proc_guia = Procedimiento.objects.create(
            titulo="Guía rápida de CertiTrack 360",
            contenido="Recorrido inicial por tablero, calendario, avisos y buscador.",
            aprobado_por=cls.gerente,
            vigente=True,
        )
        cls.proc_nda = Procedimiento.objects.create(
            titulo="Confidencialidad y datos de clientes",
            contenido="Reglas de confidencialidad y anonimización NDA.",
            aprobado_por=cls.gerente,
            vigente=True,
        )
        cls.proc_flujo = Procedimiento.objects.create(
            titulo="Flujo de un entregable",
            contenido="Estados, Poka-Yoke, adjuntos requeridos y observaciones.",
            aprobado_por=cls.gerente,
            vigente=True,
        )

    def setUp(self):
        super().setUp()
        self.doc_repo, self.v1 = repo_srv.cargar_plantilla(
            self.gerente,
            titulo="Formato de reporte mensual",
            tipo_documento=DocumentoRepositorio.TipoDocumento.REPORTE,
            archivo=_archivo("reporte_v1.docx", b"v1"),
            cliente=self.cliente,
            comentario="Versión inicial",
        )
        self.plan = servicios.guardar_plan(
            self.gerente,
            nombre="Plan Junior Operativo",
            rol=Usuario.Rol.JUNIOR,
            puesto="Asistente junior de Proyectos",
            actividades=[
                {
                    "semana": 1,
                    "orden": 1,
                    "titulo": "Recorrer CertiTrack 360",
                    "procedimiento": self.proc_guia,
                    "rol_responsable": "Senior asignado",
                    "como_se_comprueba": "Marcada por el ingresante",
                },
                {
                    "semana": 1,
                    "orden": 2,
                    "titulo": "Revisar plantilla vigente del cliente",
                    "documento": self.doc_repo,
                    "rol_responsable": "Senior asignado",
                    "como_se_comprueba": "Marcada por el ingresante",
                },
                {
                    "semana": 2,
                    "orden": 3,
                    "titulo": "Reunión de cierre del plan",
                    "enlace_interno": "/tablero/",
                    "etiqueta_recurso": "Tablero Kanban",
                    "rol_responsable": "Senior asignado",
                    "como_se_comprueba": "El responsable confirma la finalización",
                },
            ],
        )
        self.inc = servicios.asignar_plan(
            self.plan,
            ingresante=self.j1,
            responsable=self.s1,
            autor=self.gerente,
        )

    def test_asignar_crea_avances_pendientes_notifica_y_muestra_tarjeta_en_inicio(self):
        self.assertEqual(self.inc.total_actividades, 3)
        self.assertEqual(self.inc.completadas_count, 0)
        self.assertTrue(
            Notificacion.objects.filter(
                usuario=self.j1,
                tipo=Notificacion.Tipo.INCORPORACION,
                enlace=reverse("incorporacion"),
            ).exists()
        )
        self.assertTrue(
            Notificacion.objects.filter(
                usuario=self.s1,
                tipo=Notificacion.Tipo.INCORPORACION,
                enlace=reverse("incorporacion"),
            ).exists()
        )

        # j1 ve la tarjeta «Mi incorporación» en Inicio; j2 (sin incorporación) no la ve
        self.client.force_login(self.j1)
        r_j1 = self.client.get(reverse("inicio"))
        self.assertContains(r_j1, "Mi incorporación · Plan Junior Operativo")
        self.assertContains(r_j1, "0 de 3 actividades completadas")

        self.client.force_login(self.j2)
        r_j2 = self.client.get(reverse("inicio"))
        self.assertNotContains(r_j2, "Mi incorporación")

    def test_el_enlace_del_material_apunta_siempre_a_la_version_vigente(self):
        act_doc = self.plan.actividades.get(orden=2)
        self.assertEqual(act_doc.url_recurso, reverse("repositorio_descargar", args=[self.v1.pk]))
        self.assertIn("(v1)", act_doc.nombre_recurso)

        # Se sube una v2 al documento del repositorio -> la actividad apunta automáticamente a la v2 vigente
        v2 = repo_srv.subir_nueva_version(
            self.doc_repo,
            self.s1,
            archivo=_archivo("reporte_v2.docx", b"v2"),
            comentario="Actualización anual",
        )
        act_doc = ActividadPlan.objects.select_related("documento").get(pk=act_doc.pk)
        self.assertEqual(act_doc.url_recurso, reverse("repositorio_descargar", args=[v2.pk]))
        self.assertIn("(v2)", act_doc.nombre_recurso)

        self.client.force_login(self.j1)
        r = self.client.get(reverse("incorporacion"))
        self.assertContains(r, reverse("repositorio_descargar", args=[v2.pk]))
        self.assertContains(r, "(v2)")

    def test_caso_28_solo_el_ingresante_marca_su_avance_y_solo_el_responsable_confirma_con_todas_completadas(self):
        avances = list(self.inc.avances.order_by("actividad__orden"))

        # Otro usuario (j2, s1 o gerente) no puede marcar el avance del ingresante (403)
        for intruso in (self.j2, self.s1, self.gerente):
            self.client.force_login(intruso)
            r_403 = self.client.post(
                reverse("incorporacion"),
                {"accion": "avance", "avance": avances[0].pk, "estado": "COMPLETADA"},
            )
            self.assertEqual(r_403.status_code, 403)

        # El ingresante marca las 2 primeras actividades como completadas y la 3.ª en curso
        self.client.force_login(self.j1)
        self.client.post(
            reverse("incorporacion"),
            {"accion": "avance", "avance": avances[0].pk, "estado": "COMPLETADA"},
        )
        self.client.post(
            reverse("incorporacion"),
            {"accion": "avance", "avance": avances[1].pk, "estado": "COMPLETADA"},
        )
        self.client.post(
            reverse("incorporacion"),
            {"accion": "avance", "avance": avances[2].pk, "estado": "EN_CURSO"},
        )
        self.assertEqual(self.inc.completadas_count, 2)
        self.assertFalse(self.inc.todas_completadas)

        # Con una actividad pendiente/en curso, ni siquiera el responsable s1 puede confirmar la finalización
        with self.assertRaises(ValidationError) as ctx:
            servicios.confirmar_finalizacion(self.inc, self.s1)
        self.assertIn("1 actividad(es) por completar", str(ctx.exception))
        self.inc.refresh_from_db()
        self.assertFalse(self.inc.confirmada)

        # El ingresante completa la última actividad (3 de 3)
        self.client.post(
            reverse("incorporacion"),
            {"accion": "avance", "avance": avances[2].pk, "estado": "COMPLETADA"},
        )
        self.assertTrue(self.inc.todas_completadas)

        # Ni el propio ingresante j1, ni otro senior s2, ni el gerente pueden confirmar (solo el responsable s1: 403)
        for no_responsable in (self.j1, self.s2, self.gerente):
            self.client.force_login(no_responsable)
            r_denegado = self.client.post(
                reverse("incorporacion"),
                {"accion": "confirmar", "incorporacion": self.inc.pk},
            )
            self.assertEqual(r_denegado.status_code, 403)
        self.inc.refresh_from_db()
        self.assertFalse(self.inc.confirmada)

        # El responsable s1 confirma la finalización
        self.client.force_login(self.s1)
        r_ok = self.client.post(
            reverse("incorporacion"),
            {"accion": "confirmar", "incorporacion": self.inc.pk},
        )
        self.assertRedirects(r_ok, reverse("incorporacion"))
        self.inc.refresh_from_db()
        self.assertTrue(self.inc.confirmada)
        self.assertEqual(self.inc.confirmada_por, self.s1)
        self.assertIsNotNone(self.inc.confirmada_en)

        # Una vez confirmada, la tarjeta activa ya no aparece en Inicio y no admite más cambios de avance
        self.client.force_login(self.j1)
        self.assertNotContains(self.client.get(reverse("inicio")), "Mi incorporación · Plan Junior Operativo")
        with self.assertRaises(ValidationError):
            servicios.marcar_avance(avances[0], AvanceActividad.Estado.PENDIENTE, self.j1)

    def test_planes_iniciales_del_sdd_y_permisos_de_gestion(self):
        plan_jr, plan_sr = servicios.crear_planes_iniciales(autor=self.gerente)
        self.assertEqual(plan_jr.actividades.count(), 12)
        self.assertEqual(plan_sr.actividades.count(), 7)

        # Junior y Senior reciben 403 en /incorporacion/planes/
        for u in (self.j1, self.s1):
            self.client.force_login(u)
            self.assertEqual(self.client.get(reverse("incorporacion_planes")).status_code, 403)
            self.assertEqual(
                self.client.post(
                    reverse("incorporacion_planes"),
                    {"accion": "guardar_plan", "nombre": "Intruso", "rol": "JUNIOR"},
                ).status_code,
                403,
            )

        # Gerente y Admin acceden y pueden crear un plan y asignarlo desde la vista
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(reverse("incorporacion_planes")).status_code, 200)
        r_asig = self.client.post(
            reverse("incorporacion_planes"),
            {
                "accion": "asignar",
                "plan": plan_jr.pk,
                "ingresante": self.j2.pk,
                "responsable": self.s2.pk,
                "fecha_inicio": "2026-11-02",
            },
        )
        self.assertRedirects(r_asig, reverse("incorporacion_planes"))
        inc_j2 = Incorporacion.objects.get(ingresante=self.j2, plan=plan_jr)
        self.assertEqual(inc_j2.avances.count(), 12)
