"""Pruebas del asistente ampliado a procedimientos aprobados, valoración e historial (SDD Sprint 2, RF-37: HU-10, Caso 27)."""
from unittest import mock

from django.urls import reverse

from apps.clientes.models import LineaServicio
from apps.conocimiento import ollama, servicios
from apps.conocimiento.models import ConsultaAsistente, LeccionAprendida, Procedimiento
from apps.conocimiento.tests import FalsoOllama, sin_ollama, vector
from apps.entregables.models import Entregable
from apps.entregables.tests import Base

E = Entregable.Estado


class FalsoOllamaConProcedimientos(FalsoOllama):
    """Simula Ollama devolviendo embeddings por palabras clave y citando procedimientos y casos."""

    def __call__(self, ruta, cuerpo, timeout):
        self.llamadas.append(ruta)
        if ruta == "/api/embed" and self.embeddings:
            return {"embeddings": [vector(t) for t in cuerpo["input"]]}
        if ruta == "/api/chat" and self.chat:
            prompt_usuario = cuerpo["messages"][-1]["content"]
            if "[Procedimiento 1]" in prompt_usuario:
                return {
                    "message": {
                        "content": "Según el [Procedimiento 1], verifique la firma del acta y el plazo contractual."
                    }
                }
            return {"message": {"content": "Según el [Caso 1], revise la carátula antes de enviar."}}
        raise ollama.OllamaNoDisponible("simulado: no disponible")


class Caso27AsistenteAmpliadoTests(Base):
    """Caso 27 (SDD §13): el asistente cita un procedimiento; la lección de un entregable no visible no tiene enlace;
    la valoración se guarda y cada usuario ve solo su propio historial."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.linea_bpo = LineaServicio.objects.get(nombre="BPO")
        cls.entregable_visible = cls.nuevo(cls.c1, cls.j1, cls.s1, "Informe visible C1", estado=E.HECHO)
        cls.entregable_ajeno = cls.nuevo(cls.c2, cls.j2, cls.s2, "Informe reservado C2", estado=E.HECHO)

        cls.leccion_visible = LeccionAprendida.objects.create(
            entregable_origen=cls.entregable_visible,
            cliente=cls.c1.cliente,
            tipo_error="DATO_FALTANTE",
            problema="Faltaba el periodo reportado en la carátula.",
            solucion="Verificar la carátula contra la plantilla antes de enviar.",
        )
        cls.leccion_ajena = LeccionAprendida.objects.create(
            entregable_origen=cls.entregable_ajeno,
            cliente=cls.c2.cliente,
            tipo_error="PLAZO",
            problema="El acta tardó por falta de firma en el plazo acordado.",
            solucion="Recordar la firma del acta tres días antes del plazo.",
        )

        cls.proc_flujo = Procedimiento.objects.create(
            titulo="Flujo de un entregable y firma del acta",
            contenido="Para cerrar dentro del plazo, registre el cargo y solicite la firma del acta de conformidad.",
            linea_servicio=cls.linea_bpo,
            aprobado_por=cls.gerente,
            vigente=True,
        )
        cls.proc_inactivo = Procedimiento.objects.create(
            titulo="Procedimiento obsoleto de numeración",
            contenido="Regla antigua de numeración que ya no está vigente.",
            aprobado_por=cls.gerente,
            vigente=False,
        )

    def indexar(self):
        with mock.patch.object(ollama, "_post", FalsoOllamaConProcedimientos()):
            return servicios.indexar_embeddings()

    def test_indexa_lecciones_y_procedimientos_vigentes(self):
        cantidad, aviso = self.indexar()
        self.assertIsNone(aviso)
        self.assertEqual(cantidad, 3)  # 2 lecciones + 1 procedimiento vigente
        self.proc_flujo.refresh_from_db()
        self.proc_inactivo.refresh_from_db()
        self.assertIsNotNone(self.proc_flujo.embedding)
        self.assertIsNone(self.proc_inactivo.embedding)

    def test_cita_procedimiento_aprobado_y_muestra_leccion_ajena_con_cliente_pero_sin_enlace(self):
        self.indexar()
        self.client.force_login(self.j1)
        with mock.patch.object(ollama, "_post", FalsoOllamaConProcedimientos()):
            r = self.client.get(reverse("asistente"), {"q": "¿Qué hago con la firma del acta y el plazo?"})
        self.assertEqual(r.status_code, 200)

        # Cita el procedimiento vigente y no el obsoleto
        procedimientos = r.context["procedimientos"]
        self.assertEqual([p.pk for p in procedimientos], [self.proc_flujo.pk])
        self.assertContains(r, "Procedimiento 1")
        self.assertContains(r, self.proc_flujo.titulo)
        self.assertContains(r, f"{reverse('repositorio')}?pestana=procedimientos#proc-{self.proc_flujo.pk}")
        self.assertContains(r, "Según el [Procedimiento 1]")

        # Decisión C6: la lección del entregable ajeno se muestra con el nombre del cliente, pero sin enlace al entregable
        casos = r.context["casos"]
        self.assertEqual([c["leccion"] for c in casos], [self.leccion_ajena])
        self.assertFalse(casos[0]["enlace"])
        self.assertContains(r, self.c2.cliente.nombre)
        self.assertNotContains(r, reverse("entregable_detalle", args=[self.entregable_ajeno.pk]))

    def test_sin_fuentes_suficientes_no_inventa_y_orienta_a_escalar_al_senior_del_contrato(self):
        self.indexar()
        falso = FalsoOllamaConProcedimientos()
        self.client.force_login(self.j1)
        with mock.patch.object(ollama, "_post", falso):
            r = self.client.get(reverse("asistente"), {"q": "receta de cocina molecular"})
        self.assertEqual(r.context["casos"], [])
        self.assertEqual(r.context["procedimientos"], [])
        self.assertIsNone(r.context["respuesta"])
        self.assertNotIn("/api/chat", falso.llamadas)
        self.assertContains(r, "No encontré casos relacionados")
        self.assertContains(r, "Consulte con el senior de su contrato")
        self.assertContains(r, self.s1.nombre)

    def test_valoracion_se_guarda_e_historial_es_exclusivo_de_cada_usuario(self):
        self.indexar()
        # j1 realiza una consulta
        self.client.force_login(self.j1)
        with mock.patch.object(ollama, "_post", FalsoOllamaConProcedimientos()):
            r1 = self.client.get(reverse("asistente"), {"q": "periodo reportado en la carátula"})
        consulta_j1 = r1.context["consulta"]
        self.assertIsNotNone(consulta_j1)
        self.assertEqual(consulta_j1.usuario, self.j1)
        self.assertIsNone(consulta_j1.util)

        # j2 realiza otra consulta distinta
        self.client.force_login(self.j2)
        with mock.patch.object(ollama, "_post", FalsoOllamaConProcedimientos()):
            r2 = self.client.get(reverse("asistente"), {"q": "firma del acta en plazo"})
        consulta_j2 = r2.context["consulta"]
        self.assertEqual(consulta_j2.usuario, self.j2)

        # j1 valora su consulta como útil («Sí»)
        self.client.force_login(self.j1)
        r_val = self.client.post(reverse("asistente_valorar", args=[consulta_j1.pk]), {"util": "si"})
        self.assertRedirects(r_val, f"{reverse('asistente')}?consulta={consulta_j1.pk}")
        consulta_j1.refresh_from_db()
        self.assertIs(consulta_j1.util, True)

        # j1 no puede valorar ni ver la consulta de j2 (404)
        self.assertEqual(
            self.client.post(reverse("asistente_valorar", args=[consulta_j2.pk]), {"util": "no"}).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("asistente"), {"consulta": consulta_j2.pk}).status_code,
            404,
        )
        consulta_j2.refresh_from_db()
        self.assertIsNone(consulta_j2.util)

        # En «Mis consultas anteriores», j1 solo ve la suya y no la de j2
        r_hist = self.client.get(reverse("asistente"))
        self.assertEqual([c.pk for c in r_hist.context["historial_consultas"]], [consulta_j1.pk])
        self.assertContains(r_hist, "periodo reportado en la carátula")
        self.assertNotContains(r_hist, "firma del acta en plazo")

        # «Ver de nuevo» reconstruye la consulta sin duplicar el registro en el historial
        r_re = self.client.get(reverse("asistente"), {"consulta": consulta_j1.pk})
        self.assertEqual(r_re.status_code, 200)
        self.assertEqual(ConsultaAsistente.objects.filter(usuario=self.j1).count(), 1)
        self.assertContains(r_re, "Valoración registrada: Sí")

    def test_degradacion_sin_ollama_encuentra_procedimientos_por_palabras(self):
        self.client.force_login(self.j1)
        with mock.patch.object(ollama, "_post", sin_ollama):
            r = self.client.get(reverse("asistente"), {"q": "flujo entregable firma acta"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([p.pk for p in r.context["procedimientos"]], [self.proc_flujo.pk])
        self.assertContains(r, self.proc_flujo.titulo)


class GestionDeProcedimientosTests(Base):
    """Permisos y operaciones de `/procedimientos/` y de la pestaña Procedimientos en `/repositorio/`."""

    def test_junior_y_senior_reciben_403_en_procedimientos_pero_ven_pestana_en_repositorio(self):
        proc = Procedimiento.objects.create(
            titulo="Guía rápida de CertiTrack 360",
            contenido="Recorrido por inicio, tablero, calendario y buscador.",
            aprobado_por=self.gerente,
            vigente=True,
        )
        for u in (self.j1, self.s1):
            self.client.force_login(u)
            self.assertEqual(self.client.get(reverse("procedimientos")).status_code, 403)
            self.assertEqual(
                self.client.post(
                    reverse("procedimientos"),
                    {"titulo": "Intruso", "contenido": "No permitido"},
                ).status_code,
                403,
            )
            r_repo = self.client.get(reverse("repositorio"), {"pestana": "procedimientos"})
            self.assertEqual(r_repo.status_code, 200)
            self.assertContains(r_repo, proc.titulo)
            self.assertNotContains(r_repo, 'href="/procedimientos/"')

    def test_gerente_y_admin_crean_editan_y_cambian_vigencia_de_procedimientos(self):
        self.client.force_login(self.gerente)
        r_alta = self.client.post(
            reverse("procedimientos"),
            {
                "titulo": "Confidencialidad y datos de clientes",
                "contenido": "Nunca publique documentos con nombres reales ni montos.",
                "vigente": "1",
            },
        )
        self.assertRedirects(r_alta, reverse("procedimientos"))
        proc = Procedimiento.objects.get(titulo="Confidencialidad y datos de clientes")
        self.assertEqual(proc.aprobado_por, self.gerente)
        self.assertTrue(proc.vigente)

        # Editar invalida el embedding previo para que se recalcule al indexar
        Procedimiento.objects.filter(pk=proc.pk).update(embedding=[0.1, 0.2], embedding_modelo="nomic-embed-text")
        r_edit = self.client.post(
            reverse("procedimientos"),
            {
                "procedimiento": proc.pk,
                "titulo": "Confidencialidad y datos de clientes (NDA)",
                "contenido": "Verifique los cuatro puntos NDA antes de publicar un ejemplo anonimizado.",
                "vigente": "1",
            },
        )
        self.assertRedirects(r_edit, reverse("procedimientos"))
        proc.refresh_from_db()
        self.assertEqual(proc.titulo, "Confidencialidad y datos de clientes (NDA)")
        self.assertIsNone(proc.embedding)

        # Dejar sin efecto
        r_vig = self.client.post(
            reverse("procedimientos"),
            {"accion": "cambiar_vigencia", "procedimiento": proc.pk},
        )
        self.assertRedirects(r_vig, reverse("procedimientos"))
        proc.refresh_from_db()
        self.assertFalse(proc.vigente)

        # Validaciones de campos obligatorios e id inexistente
        r_err = self.client.post(reverse("procedimientos"), {"titulo": "   ", "contenido": ""})
        self.assertEqual(r_err.status_code, 200)
        self.assertContains(r_err, "Falta el título del procedimiento.")
        self.assertEqual(self.client.get(reverse("procedimientos"), {"editar": "abc"}).status_code, 404)
