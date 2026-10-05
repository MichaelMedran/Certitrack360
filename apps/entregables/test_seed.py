"""Pruebas del comando de datos simulados (SDD §16, RF-17)."""
import io
import os
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.alertas.models import Notificacion
from apps.clientes.models import Cliente, Contrato, PlantillaTDR
from apps.conocimiento import ollama
from apps.conocimiento.models import LeccionAprendida
from apps.cuentas.models import Usuario
from apps.entregables import adjuntos
from apps.entregables.models import Adjunto, Entregable, Observacion
from apps.entregables.testing import MediaTemporal
from apps.entregables.visibilidad import entregables_visibles

E = Entregable.Estado


def sin_ollama(ruta, cuerpo, timeout):
    raise ollama.OllamaNoDisponible("simulado")


class SeedDemoTests(MediaTemporal, TestCase):
    @classmethod
    def setUpTestData(cls):
        # Sin Ollama: la prueba no debe depender de un servicio que puede o no estar corriendo.
        with mock.patch.object(ollama, "_post", sin_ollama):
            cls.salida = io.StringIO()
            call_command("seed_demo", "--reset", stdout=cls.salida)

    # ---- contenido mínimo del SDD §16
    def test_usuarios_por_rol(self):
        roles = {u.username: u.rol for u in Usuario.objects.all()}
        self.assertEqual(roles, {"admin_demo": "ADMIN", "gerente_demo": "GERENTE", "senior1": "SENIOR",
                                 "senior2": "SENIOR", "junior1": "JUNIOR", "junior2": "JUNIOR", "junior3": "JUNIOR"})
        self.assertTrue(Usuario.objects.get(username="junior1").check_password("demo1234"))

    def test_clientes_ficticios_de_los_tres_sectores(self):
        self.assertEqual(Cliente.objects.count(), 6)
        self.assertEqual({c.sector for c in Cliente.objects.all()}, {"BANCA", "TELECOM", "PUBLICO"})
        for c in Cliente.objects.all():  # nombres inventados, claramente marcados como demo
            self.assertRegex(c.nombre, r"(?i)ficti|demo|prueba")

    def test_contratos_y_entregables_en_todos_los_estados(self):
        self.assertEqual(Contrato.objects.count(), 11)
        self.assertEqual(Contrato.objects.filter(activo=False).count(), 1)
        self.assertEqual(Entregable.objects.count(), 30)
        self.assertEqual({e.estado for e in Entregable.objects.all()}, set(E.values))

    def test_plazos_vencidos_y_por_vencer(self):
        activos = Entregable.objects.exclude(estado=E.HECHO)
        self.assertGreaterEqual(sum(e.urgencia == "VENCIDO" for e in activos), 3)
        self.assertGreaterEqual(sum(e.urgencia == "CRITICO" for e in activos), 3)
        self.assertGreaterEqual(sum(e.urgencia == "PROXIMO" for e in activos), 3)
        self.assertGreaterEqual(sum(e.urgencia == "NORMAL" for e in activos), 3)

    def test_plantillas_con_campos_y_adjuntos_distintos(self):
        self.assertEqual(PlantillaTDR.objects.count(), 4)
        self.assertGreaterEqual(len({tuple(p.adjuntos_requeridos) for p in PlantillaTDR.objects.all()}), 3)
        self.assertGreaterEqual(len({tuple(c["nombre"] for c in p.campos_requeridos) for p in PlantillaTDR.objects.all()}), 4)
        self.assertEqual(PlantillaTDR.objects.filter(cliente__isnull=False).count(), 1)  # una específica por cliente
        tipos = {c["tipo"] for p in PlantillaTDR.objects.all() for c in p.campos_requeridos}
        self.assertEqual(tipos, {"texto", "texto_largo", "numero", "fecha", "opcion"})

    def test_los_datos_cumplen_los_campos_de_su_plantilla(self):
        for e in Entregable.objects.select_related("plantilla"):
            self.assertEqual(set(e.datos), {c["nombre"] for c in e.plantilla.campos_requeridos}, e.titulo)
            self.assertTrue(all(str(v).strip() for v in e.datos.values()), e.titulo)

    def test_observaciones_de_todos_los_tipos_y_varias_resueltas(self):
        self.assertEqual({o.tipo_error for o in Observacion.objects.all()},
                         {"DATO_FALTANTE", "FORMATO", "PLAZO", "CONTENIDO", "OTRO"})
        self.assertEqual({o.tipo_error for o in Observacion.objects.filter(resuelta=False)},
                         {"DATO_FALTANTE", "FORMATO", "PLAZO", "CONTENIDO", "OTRO"})  # abiertas de cada tipo (filtros)
        self.assertGreaterEqual(Observacion.objects.filter(resuelta=True).count(), 10)
        self.assertFalse(Observacion.objects.filter(resuelta=True, solucion="").exists())

    def test_notificaciones_de_ejemplo_de_cada_tipo(self):
        self.assertEqual({n.tipo for n in Notificacion.objects.all()}, {"VENCIMIENTO", "OBSERVACION", "ASIGNACION", "VERIFICACION"})
        self.assertTrue(Notificacion.objects.filter(leida=False).exists())
        self.assertTrue(Notificacion.objects.filter(leida=True).exists())

    # ---- archivos ficticios
    def test_hay_archivos_ficticios_y_existen_en_disco(self):
        self.assertGreaterEqual(Adjunto.objects.count(), 30)
        for a in Adjunto.objects.all():
            self.assertTrue(os.path.exists(a.archivo.path), a.archivo.name)
            self.assertLess(a.archivo.size, 10_000)  # diminutos
        with Adjunto.objects.filter(nombre_original__endswith=".txt").first().archivo.open("rb") as f:
            self.assertIn(b"ficticio", f.read())
        with Adjunto.objects.filter(nombre_original__endswith=".pdf").first().archivo.open("rb") as f:
            self.assertTrue(f.read().startswith(b"%PDF"))

    def test_algunos_adjuntos_tienen_varias_versiones(self):
        self.assertTrue(Adjunto.objects.filter(version__gte=2).exists())
        for a in Adjunto.objects.filter(version__gt=1):
            self.assertTrue(Adjunto.objects.filter(entregable=a.entregable, tipo=a.tipo, version=a.version - 1).exists())

    def test_los_tipos_de_adjunto_son_variados(self):
        self.assertEqual(set(Adjunto.objects.values_list("tipo", flat=True)), {"TDR", "BORRADOR", "VERSION_FINAL", "EVIDENCIA"})

    def test_ningun_entregable_en_verificacion_o_despues_incumple_los_adjuntos_requeridos(self):
        for e in Entregable.objects.filter(estado__in=[E.VERIFICACION_SENIOR, E.LISTO_PARA_ENTREGA, E.HECHO]):
            self.assertEqual(adjuntos.faltantes_requeridos(e), [], e.titulo)

    def test_hay_entregables_en_proceso_bloqueados_por_adjuntos_para_la_demo(self):
        bloqueados = [e for e in Entregable.objects.filter(estado=E.EN_PROCESO) if adjuntos.faltantes_requeridos(e)]
        self.assertGreaterEqual(len(bloqueados), 2)

    def test_el_resumen_indica_que_tarjetas_demuestran_el_bloqueo(self):
        salida = self.salida.getvalue()
        self.assertIn("bloqueo por adjuntos faltantes", salida)
        bloqueados = {e.titulo: e.junior_asignado.username
                      for e in Entregable.objects.filter(estado=E.EN_PROCESO) if adjuntos.faltantes_requeridos(e)}
        self.assertGreaterEqual(len(bloqueados), 2)
        for titulo, junior in bloqueados.items():
            self.assertIn(f"«{titulo}» ({junior})", salida)

    def test_los_archivos_estan_ordenados_por_cliente_contrato_y_entregable(self):
        for a in Adjunto.objects.select_related("entregable__contrato__cliente"):
            partes = a.archivo.name.split("/")
            self.assertTrue(partes[0].startswith(f"{a.entregable.contrato.cliente_id}-"))
            self.assertEqual(partes[2], f"entregable-{a.entregable_id}")

    # ---- fase 2
    def test_entre_15_y_20_lecciones_con_su_caso_de_origen(self):
        self.assertTrue(15 <= LeccionAprendida.objects.count() <= 20)
        for leccion in LeccionAprendida.objects.select_related("entregable_origen", "observacion_origen"):
            self.assertEqual(leccion.entregable_origen.estado, E.HECHO)
            self.assertTrue(leccion.observacion_origen.resuelta)
            self.assertEqual(leccion.cliente, leccion.entregable_origen.contrato.cliente)

    def test_los_comentarios_de_las_lecciones_por_sector_son_coherentes(self):
        for leccion in LeccionAprendida.objects.all():
            if "bancario" in leccion.problema:
                self.assertEqual(leccion.cliente.sector, "BANCA")
            if "telecomunicaciones" in leccion.problema:
                self.assertEqual(leccion.cliente.sector, "TELECOM")
            if "sector público" in leccion.problema:
                self.assertEqual(leccion.cliente.sector, "PUBLICO")

    def test_sin_ollama_avisa_como_activar_la_busqueda_por_significado(self):
        self.assertIn("indexar_lecciones", self.salida.getvalue())
        self.assertFalse(LeccionAprendida.objects.filter(embedding__isnull=False).exists())

    def test_el_asistente_cita_un_caso_ficticio_existente(self):
        self.client.login(username="gerente_demo", password="demo1234")
        with mock.patch.object(ollama, "_post", sin_ollama):
            r = self.client.get(reverse("asistente"), {"q": "falta el periodo reportado en el informe"})
        self.assertTrue(r.context["casos"])
        self.assertContains(r, "Caso 1")
        primero = r.context["casos"][0]["leccion"]
        self.assertIn("periodo", primero.problema.lower())
        self.assertContains(r, f"Contrato {primero.entregable_origen.contrato.numero_contrato}")

    # ---- cada rol ve solo lo suyo con los datos de demostración
    def test_visibilidad_con_los_datos_de_demostracion(self):
        total = Entregable.objects.count()
        gerente = Usuario.objects.get(username="gerente_demo")
        self.assertEqual(entregables_visibles(gerente).count(), total)
        for junior in Usuario.objects.filter(rol="JUNIOR"):
            visibles = entregables_visibles(junior)
            self.assertTrue(0 < visibles.count() < total)
            self.assertFalse(visibles.exclude(junior_asignado=junior).exists())
        for senior in Usuario.objects.filter(rol="SENIOR"):
            self.assertTrue(0 < entregables_visibles(senior).count() < total)


class SeedIdempotenciaTests(MediaTemporal, TestCase):
    def sembrar(self, *args):
        salida = io.StringIO()
        with mock.patch.object(ollama, "_post", sin_ollama):
            call_command("seed_demo", *args, stdout=salida)
        return salida.getvalue()

    def cifras(self):
        return (Usuario.objects.count(), Cliente.objects.count(), Contrato.objects.count(), Entregable.objects.count(),
                Adjunto.objects.count(), Observacion.objects.count(), Notificacion.objects.count(), LeccionAprendida.objects.count())

    def test_con_la_base_vacia_deja_todo_listo(self):
        self.sembrar()
        self.assertEqual(Entregable.objects.count(), 30)

    def test_varias_ejecuciones_no_duplican(self):
        self.sembrar()
        antes = self.cifras()
        mensaje = self.sembrar()
        self.assertIn("Ya existen datos", mensaje)
        self.assertEqual(self.cifras(), antes)

    def test_reset_recrea_y_borra_los_archivos_anteriores(self):
        self.sembrar()
        rutas = {a.archivo.path for a in Adjunto.objects.all()}
        self.assertTrue(all(os.path.exists(r) for r in rutas))
        with self.captureOnCommitCallbacks(execute=True):  # en pruebas hay que forzar lo que ocurre al confirmar
            self.sembrar("--reset")
        self.assertEqual(Entregable.objects.count(), 30)
        self.assertFalse(any(os.path.exists(r) for r in rutas))  # no quedan huérfanos de la siembra anterior
        self.assertEqual(Adjunto.objects.count(), len({a.archivo.path for a in Adjunto.objects.all()}))

    def test_reset_sin_datos_previos_funciona(self):
        self.sembrar("--reset")
        self.assertEqual(Usuario.objects.count(), 7)
