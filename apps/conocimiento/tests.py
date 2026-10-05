"""Pruebas del asistente de lecciones aprendidas (SDD RF-19, caso 12 de la sección 17.2).

No hay un Ollama real en las pruebas: se simula con `FalsoOllama`, que convierte cada texto en un vector según las
palabras clave que contiene, de modo que «parecido por significado» sea predecible.
"""
import io
import urllib.error
from unittest import mock

from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from apps.conocimiento import ollama, servicios
from apps.conocimiento.models import LeccionAprendida
from apps.entregables import servicios as flujo
from apps.entregables.models import Entregable, Observacion
from apps.entregables.tests import Base

E = Entregable.Estado
CLAVES = ["periodo", "firma", "numeracion", "plazo", "contenido"]


def vector(texto):
    texto = texto.lower()
    return [1.0 if clave in texto else 0.0 for clave in CLAVES] + [0.01]


class FalsoOllama:
    """Reemplaza ollama._post: embeddings por palabras clave y una respuesta fija del modelo de lenguaje."""

    def __init__(self, embeddings=True, chat=True):
        self.embeddings, self.chat, self.llamadas = embeddings, chat, []

    def __call__(self, ruta, cuerpo, timeout):
        self.llamadas.append(ruta)
        if ruta == "/api/embed" and self.embeddings:
            return {"embeddings": [vector(t) for t in cuerpo["input"]]}
        if ruta == "/api/chat" and self.chat:
            return {"message": {"content": "Según el [Caso 1], revise la carátula antes de enviar."}}
        raise ollama.OllamaNoDisponible("simulado: no disponible")


def sin_ollama(ruta, cuerpo, timeout):
    raise ollama.OllamaNoDisponible("simulado: sin conexión")


class LeccionesBase(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.cerrado = cls.nuevo(cls.c1, cls.j1, cls.s1, "Informe cerrado", estado=E.LISTO_PARA_ENTREGA)
        cls.resuelta = Observacion.objects.create(
            entregable=cls.cerrado, autor=cls.s1, tipo_error="DATO_FALTANTE", resuelta=True,
            descripcion="Faltaba el periodo reportado en la carátula.",
            solucion="Verificar la carátula contra la plantilla antes de enviar.")
        cls.abierta = Observacion.objects.create(
            entregable=cls.cerrado, autor=cls.s1, tipo_error="FORMATO", descripcion="Falta la numeración de páginas.")


class GeneracionTests(LeccionesBase):
    def test_al_cerrar_el_entregable_se_genera_una_leccion_por_observacion_resuelta(self):
        self.assertEqual(LeccionAprendida.objects.count(), 0)
        flujo.mover(self.cerrado, E.HECHO, self.s1)
        leccion = LeccionAprendida.objects.get()
        self.assertEqual(leccion.entregable_origen, self.cerrado)
        self.assertEqual(leccion.observacion_origen, self.resuelta)
        self.assertEqual(leccion.cliente, self.cliente)
        self.assertEqual((leccion.tipo_error, leccion.problema), ("DATO_FALTANTE", self.resuelta.descripcion))
        self.assertEqual(leccion.solucion, self.resuelta.solucion)

    def test_las_observaciones_abiertas_no_generan_leccion(self):
        flujo.mover(self.cerrado, E.HECHO, self.s1)
        self.assertFalse(LeccionAprendida.objects.filter(observacion_origen=self.abierta).exists())

    def test_cerrar_no_genera_lecciones_mientras_el_entregable_no_este_hecho(self):
        self.assertEqual(servicios.generar_lecciones_pendientes(), 0)

    def test_no_se_duplican(self):
        flujo.mover(self.cerrado, E.HECHO, self.s1)
        self.assertEqual(servicios.generar_lecciones(self.cerrado), 0)
        self.assertEqual(servicios.generar_lecciones_pendientes(), 0)
        self.assertEqual(LeccionAprendida.objects.count(), 1)

    def test_una_observacion_resuelta_despues_de_cerrar_se_recoge_al_indexar(self):
        flujo.mover(self.cerrado, E.HECHO, self.s1)
        Observacion.objects.filter(pk=self.abierta.pk).update(resuelta=True, solucion="Usar el pie de página de la plantilla.")
        with mock.patch.object(ollama, "_post", FalsoOllama()):
            nuevas, indexadas, aviso = servicios.indexar_lecciones()
        self.assertEqual((nuevas, indexadas, aviso), (1, 2, None))

    def test_una_solucion_en_blanco_no_genera_leccion(self):
        Observacion.objects.filter(pk=self.resuelta.pk).update(solucion="   ")
        flujo.mover(self.cerrado, E.HECHO, self.s1)
        self.assertEqual(LeccionAprendida.objects.count(), 0)


class IndexacionTests(LeccionesBase):
    def setUp(self):
        flujo.mover(self.cerrado, E.HECHO, self.s1)

    def test_calcula_y_guarda_el_embedding(self):
        falso = FalsoOllama()
        with mock.patch.object(ollama, "_post", falso):
            self.assertEqual(servicios.indexar_embeddings(), (1, None))
        leccion = LeccionAprendida.objects.get()
        self.assertEqual(leccion.embedding, vector(leccion.texto_indexable))
        self.assertEqual(leccion.embedding_modelo, "nomic-embed-text")

    def test_no_recalcula_lo_ya_indexado(self):
        falso = FalsoOllama()
        with mock.patch.object(ollama, "_post", falso):
            servicios.indexar_embeddings()
            servicios.indexar_embeddings()
        self.assertEqual(falso.llamadas, ["/api/embed"])

    def test_recalcula_si_cambia_el_modelo_de_embeddings(self):
        with mock.patch.object(ollama, "_post", FalsoOllama()):
            servicios.indexar_embeddings()
            with override_settings(EMBED_MODEL="otro-modelo"):
                self.assertEqual(servicios.indexar_embeddings(), (1, None))
        self.assertEqual(LeccionAprendida.objects.get().embedding_modelo, "otro-modelo")

    def test_sin_ollama_avisa_y_no_falla(self):
        with mock.patch.object(ollama, "_post", sin_ollama):
            cantidad, aviso = servicios.indexar_embeddings()
        self.assertEqual(cantidad, 0)
        self.assertIn("No se pudieron calcular los embeddings", aviso)
        self.assertIsNone(LeccionAprendida.objects.get().embedding)

    def test_el_comando_informa(self):
        salida, errores = io.StringIO(), io.StringIO()
        with mock.patch.object(ollama, "_post", FalsoOllama()):
            call_command("indexar_lecciones", stdout=salida, stderr=errores)
        self.assertIn("Embeddings calculados: 1", salida.getvalue())
        self.assertEqual(errores.getvalue(), "")
        with mock.patch.object(ollama, "_post", sin_ollama):
            LeccionAprendida.objects.update(embedding=None)
            call_command("indexar_lecciones", stdout=salida, stderr=errores)
        self.assertIn("No se pudieron calcular", errores.getvalue())

    def test_respuesta_incompleta_de_ollama(self):
        incompleta = lambda ruta, cuerpo, timeout: {"embeddings": []}
        with mock.patch.object(ollama, "_post", incompleta), self.assertRaises(ollama.OllamaNoDisponible):
            ollama.embeddings(["hola"])

    def test_solo_acepta_http(self):
        with override_settings(OLLAMA_URL="file:///etc/passwd"), self.assertRaises(ollama.OllamaNoDisponible):
            ollama.embeddings(["hola"])


class ConsultaTests(Base):
    """Caso 12: una consulta sobre un error frecuente devuelve una respuesta que cita un caso ficticio existente."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.visible = cls.nuevo(cls.c1, cls.j1, cls.s1, "Informe visible", estado=E.HECHO)
        cls.ajeno = cls.nuevo(cls.c2, cls.j2, cls.s2, "Informe ajeno", estado=E.HECHO)
        crear = lambda entregable, tipo, problema, solucion: LeccionAprendida.objects.create(
            entregable_origen=entregable, cliente=entregable.contrato.cliente, tipo_error=tipo,
            problema=problema, solucion=solucion)
        cls.periodo = crear(cls.visible, "DATO_FALTANTE", "Faltaba el periodo reportado en la carátula.",
                            "Verificar la carátula contra la plantilla.")
        cls.firma = crear(cls.ajeno, "OTRO", "No tenía la firma digital que exige el TDR.",
                          "Coordinar con el firmante autorizado.")

    def indexar(self):
        with mock.patch.object(ollama, "_post", FalsoOllama()):
            servicios.indexar_embeddings()

    def consultar(self, usuario, pregunta, ollama_falso=None):
        self.client.force_login(usuario)
        with mock.patch.object(ollama, "_post", ollama_falso or FalsoOllama()):
            return self.client.get(reverse("asistente"), {"q": pregunta})

    def test_busca_por_significado_cita_el_caso_y_redacta_la_respuesta(self):
        self.indexar()
        r = self.consultar(self.j1, "¿Qué hago si olvidé el periodo del informe?")
        casos = r.context["casos"]
        self.assertEqual([c["leccion"] for c in casos], [self.periodo])
        self.assertEqual(r.context["respuesta"], "Según el [Caso 1], revise la carátula antes de enviar.")
        self.assertIsNone(r.context["aviso"])
        self.assertContains(r, "Caso 1")
        self.assertContains(r, self.periodo.problema)
        self.assertContains(r, "Contrato C1")

    def test_el_enlace_al_caso_respeta_los_permisos(self):
        self.indexar()
        r = self.consultar(self.j1, "falta la firma")
        [caso] = r.context["casos"]
        self.assertEqual(caso["leccion"], self.firma)
        self.assertFalse(caso["enlace"])  # el entregable de origen es de otro contrato
        self.assertNotContains(r, reverse("entregable_detalle", args=[self.ajeno.pk]))
        r = self.consultar(self.gerente, "falta la firma")
        self.assertTrue(r.context["casos"][0]["enlace"])
        self.assertContains(r, reverse("entregable_detalle", args=[self.ajeno.pk]))

    def test_si_no_hay_casos_relevantes_lo_dice_y_no_inventa(self):
        self.indexar()
        falso = FalsoOllama()
        r = self.consultar(self.j1, "receta de cocina", falso)
        self.assertEqual(r.context["casos"], [])
        self.assertIsNone(r.context["respuesta"])
        self.assertContains(r, "No encontré casos relacionados")
        self.assertNotIn("/api/chat", falso.llamadas)  # sin casos no se le pide nada al modelo

    def test_sin_indice_usa_palabras_y_lo_avisa(self):
        r = self.consultar(self.j1, "periodo reportado", FalsoOllama())
        self.assertEqual([c["leccion"] for c in r.context["casos"]], [self.periodo])
        self.assertEqual(r.context["aviso"], servicios.AVISO_SIN_INDICE)
        self.assertContains(r, "indexar_lecciones")

    def test_sin_ollama_degrada_con_aviso_y_la_plataforma_sigue(self):
        self.indexar()
        r = self.consultar(self.j1, "periodo reportado", sin_ollama)
        self.assertEqual(r.status_code, 200)
        self.assertEqual([c["leccion"] for c in r.context["casos"]], [self.periodo])
        self.assertEqual(r.context["aviso"], servicios.AVISO_SIN_OLLAMA)
        self.assertIsNone(r.context["respuesta"])
        self.assertContains(r, "Ollama")
        for nombre in ("inicio", "tablero", "calendario", "entregables", "notificaciones"):  # RNF-09
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, nombre)

    def test_solo_falla_la_redaccion(self):
        self.indexar()
        r = self.consultar(self.j1, "periodo reportado", FalsoOllama(chat=False))
        self.assertEqual([c["leccion"] for c in r.context["casos"]], [self.periodo])
        self.assertEqual(r.context["aviso"], servicios.AVISO_SIN_REDACCION)

    def test_el_prompt_usa_solo_los_casos_encontrados(self):
        mensajes = servicios._prompt("¿y ahora?", [self.periodo])
        self.assertIn("SOLO los casos dados", mensajes[0]["content"])
        self.assertIn("[Caso 1]", mensajes[1]["content"])
        self.assertIn(self.periodo.problema, mensajes[1]["content"])
        self.assertNotIn(self.firma.problema, mensajes[1]["content"])

    @override_settings(ASSISTANT_MIN_SIMILARITY=0.0)
    def test_el_umbral_de_similitud_se_configura(self):
        self.indexar()
        r = self.consultar(self.j1, "receta de cocina")
        self.assertNotEqual(r.context["casos"], [])

    def test_requiere_sesion(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("asistente"), {"q": "x"}).status_code, 302)

    def test_busqueda_lexica_sin_resultados(self):
        self.assertEqual(servicios.buscar_lexico("xyzzy"), [])

    def test_coseno(self):
        self.assertAlmostEqual(servicios.coseno([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(servicios.coseno([1, 0], [0, 1]), 0.0)
        self.assertEqual(servicios.coseno([0, 0], [1, 1]), 0.0)


class ErroresDeRedTests(Base):
    def test_un_error_de_red_se_convierte_en_ollama_no_disponible(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("sin red")):
            with self.assertRaises(ollama.OllamaNoDisponible):
                ollama.responder([{"role": "user", "content": "hola"}])

    def test_respuesta_no_json(self):
        with mock.patch("urllib.request.urlopen", side_effect=ValueError("no es json")):
            with self.assertRaises(ollama.OllamaNoDisponible):
                ollama.embeddings(["hola"])
