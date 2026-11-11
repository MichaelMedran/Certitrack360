"""Pruebas del comando de datos simulados (SDD §16, RF-17)."""
import io
import os
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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
        # Ajuste del Sprint 3: la alerta urgente, la verificación de factura y el reporte de avance también dejan avisos.
        self.assertEqual({n.tipo for n in Notificacion.objects.all()},
                         {"VENCIMIENTO", "OBSERVACION", "ASIGNACION", "VERIFICACION", "URGENTE", "FACTURA", "REPORTE"})
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
        # Ajuste derivado de RF-29 (SDD §11.3): el seed crea el cargo y el acta de los entregables cerrados.
        self.assertEqual(set(Adjunto.objects.values_list("tipo", flat=True)),
                         {"TDR", "BORRADOR", "VERSION_FINAL", "EVIDENCIA", "CARGO_RECEPCION", "ACTA_CONFORMIDAD", "EXPORTACION"})

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

    # ---- Sprint 2 (RF-29): los entregables cerrados tienen cargo, entrega y acta
    def test_los_siete_entregados_tienen_entrega_con_cargo_y_la_version_enviada_bloqueada(self):
        from apps.entregables.models import Entrega

        hechos = Entregable.objects.filter(estado=E.HECHO)
        self.assertEqual(hechos.count(), 7)
        for e in hechos:
            entrega = e.entregas.get()
            self.assertEqual(entrega.numero, 1)
            self.assertEqual(entrega.cargo.tipo, "CARGO_RECEPCION")
            self.assertTrue(entrega.cargo.bloqueado and entrega.version_enviada.bloqueado, e.codigo)
            self.assertEqual(entrega.version_enviada.tipo, "VERSION_FINAL")
            self.assertEqual(entrega.cierre.estado_nuevo, E.HECHO)
            self.assertLessEqual(entrega.fecha_entrega, timezone.localdate())
            self.assertGreaterEqual(entrega.fecha_entrega, e.fecha_recepcion)
        self.assertEqual(set(Entrega.objects.values_list("acta_estado", flat=True)), {"RECIBIDA", "PENDIENTE", "OBSERVADA"})
        for entrega in Entrega.objects.exclude(acta_estado="PENDIENTE"):
            self.assertEqual(entrega.acta.tipo, "ACTA_CONFORMIDAD")
            self.assertTrue(entrega.acta.bloqueado)
        self.assertFalse(Entrega.objects.filter(acta_estado="PENDIENTE", acta__isnull=False).exists())
        self.assertFalse(Entregable.objects.exclude(estado=E.HECHO).filter(entregas__isnull=False).exists())

    def test_el_seed_no_genera_avisos_de_acta_ni_deja_versiones_bloqueadas_sin_entrega(self):
        self.assertFalse(Notificacion.objects.filter(tipo="ACTA").exists())
        for a in Adjunto.objects.filter(bloqueado=True):
            self.assertEqual(a.entregable.estado, E.HECHO)

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

    # ---- ampliación del Sprint 2 (SDD §12.1, S2-H13)
    def test_sprint_2_datos_simulados_completos(self):
        from apps.conocimiento.models import Procedimiento
        from apps.cuentas.models import Ausencia
        from apps.entregables.models import Entrega, RegistroTiempo, ResponsableApoyo
        from apps.equipo.models import AvanceActividad, Incorporacion, PlanIncorporacion
        from apps.levantamiento.models import FichaLevantamiento
        from apps.repositorio.models import DocumentoRepositorio, VersionDocumento

        # Puestos en los usuarios y ausencia registrada
        self.assertFalse(Usuario.objects.filter(puesto="").exists())
        self.assertEqual(Ausencia.objects.count(), 1)

        # Observaciones en los tres estados (PENDIENTE, EN_CORRECCION y RESUELTA)
        self.assertEqual(
            set(Observacion.objects.values_list("estado", flat=True)),
            {"PENDIENTE", "EN_CORRECCION", "RESUELTA"},
        )

        # Acta pendiente vencida (> 5 días) lista para demostrar la alerta
        pendiente = Entrega.objects.get(acta_estado="PENDIENTE")
        self.assertGreater((timezone.localdate() - pendiente.fecha_entrega).days, 5)

        # Dos fichas de levantamiento: una en borrador y otra confirmada con foto inicial y entregables vinculados
        self.assertEqual(FichaLevantamiento.objects.count(), 2)
        self.assertEqual(
            set(FichaLevantamiento.objects.values_list("estado", flat=True)),
            {"BORRADOR", "CONFIRMADA"},
        )
        confirmada = FichaLevantamiento.objects.get(estado="CONFIRMADA")
        self.assertTrue(confirmada.estado_inicial)
        self.assertTrue(os.path.exists(confirmada.archivo_tdr.path))
        self.assertGreater(confirmada.items.first().entregables_generados.count(), 0)

        # Responsables de apoyo (activos e histórico) y registros de tiempo de las 3 etapas (alguno manual)
        self.assertGreaterEqual(ResponsableApoyo.objects.filter(activo=True).count(), 2)
        self.assertTrue(ResponsableApoyo.objects.filter(activo=False).exists())
        self.assertEqual(
            set(RegistroTiempo.objects.values_list("etapa", flat=True)),
            {"RECOPILACION", "CONSOLIDACION", "REVISION"},
        )
        self.assertTrue(RegistroTiempo.objects.filter(manual=True).exclude(motivo="").exists())

        # Repositorio: 8 documentos (plantillas de cliente con dos versiones, genéricas y ejemplos anonimizados)
        self.assertEqual(DocumentoRepositorio.objects.count(), 8)
        self.assertTrue(VersionDocumento.objects.filter(numero=2, vigente=True).exists())
        self.assertTrue(
            DocumentoRepositorio.objects.filter(
                categoria=DocumentoRepositorio.Categoria.EJEMPLO_ANONIMIZADO
            ).exists()
        )
        for v in VersionDocumento.objects.all():
            self.assertTrue(os.path.exists(v.archivo.path), v.archivo.name)

        # 5 procedimientos aprobados (incluidos los 3 citados en §7.12)
        self.assertEqual(Procedimiento.objects.filter(vigente=True).count(), 5)
        for titulo in (
            "Guía rápida de CertiTrack 360",
            "Confidencialidad y datos de clientes",
            "Flujo de un entregable",
        ):
            self.assertTrue(Procedimiento.objects.filter(titulo=titulo, vigente=True).exists(), titulo)

        # Los dos planes de incorporación (§7.12) y una incorporación en curso con avances en los 3 estados
        self.assertEqual(PlanIncorporacion.objects.count(), 2)
        self.assertEqual(
            PlanIncorporacion.objects.get(nombre="Asistente junior de Proyectos").actividades.count(),
            12,
        )
        self.assertEqual(
            PlanIncorporacion.objects.get(nombre="Senior de Proyectos").actividades.count(),
            7,
        )
        inc = Incorporacion.objects.get()
        self.assertFalse(inc.confirmada)
        self.assertEqual(inc.completadas_count, 5)
        self.assertEqual(
            set(inc.avances.values_list("estado", flat=True)),
            set(AvanceActividad.Estado.values),
        )


class SeedSprint3Tests(MediaTemporal, TestCase):
    """Con `seed_demo --reset` sobre una base vacía queda demostrable todo el Sprint 3 (SDD del Sprint 3, §12.1)."""

    @classmethod
    def setUpTestData(cls):
        with mock.patch.object(ollama, "_post", sin_ollama):
            cls.salida = io.StringIO()
            call_command("seed_demo", "--reset", stdout=cls.salida)

    def test_clientes_de_los_tres_tipos_y_entregables_de_las_tres_prioridades(self):
        from apps.entregables import prioridad

        self.assertEqual({c.tipo for c in Cliente.objects.all()}, {"ESTRATEGICO", "REGULAR", "OCASIONAL"})
        niveles = {
            prioridad.calcular(e.plazo, e.estado, e.contrato.cliente.tipo, e.alertas_urgentes.abiertas().exists())
            for e in Entregable.objects.exclude(estado=E.HECHO).select_related("contrato__cliente")
        }
        self.assertEqual(niveles, {prioridad.ALTA, prioridad.MEDIA, prioridad.BAJA})

    def test_etiquetas_en_contratos_y_entregables(self):
        from apps.etiquetas.models import Etiqueta

        self.assertEqual(Etiqueta.objects.filter(linea_servicio__isnull=False).count(), 5)
        self.assertEqual(set(Etiqueta.objects.filter(linea_servicio__isnull=True).values_list("nombre", flat=True)),
                         {"Auditoría externa", "Cliente en observación"})
        self.assertEqual(Etiqueta.contratos.through.objects.values("contrato_id").distinct().count(), 10)
        self.assertGreaterEqual(Etiqueta.entregables.through.objects.values("entregable_id").distinct().count(), 8)
        self.client.login(username="gerente_demo", password="demo1234")
        etiqueta = Etiqueta.objects.get(nombre="Auditoría externa")
        r = self.client.get(reverse("entregables"), {"etiqueta": etiqueta.pk})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Auditoría externa")

    def test_guardia_y_alertas_urgentes_abierta_y_aceptada(self):
        from apps.urgencias.models import AlertaUrgente

        self.assertEqual(list(Usuario.objects.filter(de_guardia=True).values_list("username", flat=True)), ["senior2"])
        abierta = AlertaUrgente.objects.abiertas().get()
        self.assertGreaterEqual(abierta.destinatarios.count(), 3)
        self.assertEqual(abierta.lecturas.count(), 1)  # solo leyó el junior: los demás siguen pendientes
        aceptada = AlertaUrgente.objects.exclude(aceptada_por=None).get()
        self.assertEqual(aceptada.aceptada_por.username, "senior2")
        self.assertTrue(aceptada.fuera_de_horario)
        self.assertIsNotNone(aceptada.cerrada_en)
        self.assertTrue(Notificacion.objects.filter(tipo="URGENTE", leida=False).exists())

    def test_checklists_por_tdr_con_distintos_porcentajes_y_un_envio_con_advertencia(self):
        from apps.checklists import tdr

        porcentajes = {tdr.resumen(e)["porcentaje"] for e in Entregable.objects.all() if e.checklist_tdr.exists()}
        self.assertIn(0, porcentajes)
        self.assertIn(100, porcentajes)
        self.assertGreaterEqual(len(porcentajes), 5)
        self.assertTrue(any(e.checklist_tdr.filter(origen="FICHA").exists() for e in Entregable.objects.all()))
        self.assertTrue(any(e.checklist_tdr.filter(origen="MANUAL").exists() for e in Entregable.objects.all()))
        # El entregable En proceso con obligatorios pendientes pide confirmación al enviarlo a revisión.
        codigo = self.salida.getvalue().split("Checklists por TDR")[1].split(" tiene obligatorios")[0].split()[-1]
        e = Entregable.objects.get(codigo=codigo)
        self.assertEqual(e.estado, E.EN_PROCESO)
        self.assertTrue(tdr.obligatorios_pendientes(e).exists())
        self.assertEqual(adjuntos.faltantes_requeridos(e), [])

    def test_revisiones_de_calidad_conforme_y_no_conforme(self):
        from apps.checklists import calidad
        from apps.checklists.models import ItemCalidad, RevisionCalidad

        self.assertEqual(set(RevisionCalidad.objects.values_list("resultado", flat=True)), {"CONFORME", "NO_CONFORME"})
        self.assertTrue(ItemCalidad.objects.filter(cliente__isnull=False).exists())
        no_conforme = RevisionCalidad.objects.get(resultado="NO_CONFORME")
        self.assertTrue(no_conforme.respuestas.exclude(observacion="").exists())
        self.assertEqual(no_conforme.entregable.estado, E.EN_PROCESO)  # lo devolvió a En proceso
        # En revisión quedan unos con su revisión conforme (aprobables) y uno al que le falta la revisión.
        en_revision = list(Entregable.objects.filter(estado=E.VERIFICACION_SENIOR))
        con_revision = [e for e in en_revision if calidad.revision_vigente(e) is not None]
        sin_revision = [e for e in en_revision if calidad.revision_vigente(e) is None]
        self.assertTrue(con_revision and sin_revision)
        self.assertEqual(calidad.condicion(sin_revision[0], E.LISTO_PARA_ENTREGA, None, {}), calidad.MOTIVO_SIN_REVISION)
        self.assertIsNone(calidad.condicion(con_revision[0], E.LISTO_PARA_ENTREGA, None, {}))

    def test_facturas_simuladas_correcta_de_otro_cliente_justificada_y_anulada(self):
        from apps.facturacion import verificacion
        from apps.facturacion.models import FacturaSimulada, VerificacionFactura

        self.assertEqual(FacturaSimulada.objects.count(), 6)
        self.assertEqual(set(FacturaSimulada.objects.values_list("estado", flat=True)), {"EMITIDA", "ANULADA", "PAGADA"})
        resultados = dict(VerificacionFactura.objects.values_list("resultado", "justificacion"))
        self.assertEqual(set(resultados), {"CORRECTA", "OTRO_CLIENTE", "ANULADA"})
        self.assertTrue(resultados["OTRO_CLIENTE"])  # justificada por el senior
        self.assertFalse(resultados["ANULADA"])  # sin justificar: impide aprobar
        anulada = VerificacionFactura.objects.get(resultado="ANULADA").entregable
        self.assertIn("anulada", verificacion.condicion(anulada, E.LISTO_PARA_ENTREGA, None, {}).lower())

    def test_dos_exportaciones_guardadas_como_versiones(self):
        exportaciones = list(Adjunto.objects.filter(tipo="EXPORTACION").order_by("version"))
        self.assertEqual([a.version for a in exportaciones], [1, 2])
        self.assertEqual(len({a.entregable_id for a in exportaciones}), 1)
        self.assertEqual([a.nombre_original.rsplit(".", 1)[1] for a in exportaciones], ["pdf", "xlsx"])
        for a in exportaciones:
            self.assertTrue(os.path.exists(a.archivo.path))

    def test_extraccion_pendiente_con_un_campo_sin_encontrar(self):
        from apps.extraccion.models import Extraccion

        extraccion = Extraccion.objects.get()
        self.assertIsNone(extraccion.aplicada_en)
        self.assertTrue(os.path.exists(extraccion.archivo.path))
        estados = {c["estado"] for c in extraccion.campos}
        self.assertIn("ok", estados)
        self.assertIn("no_encontrado", estados)
        self.client.login(username=extraccion.usuario.username, password="demo1234")
        self.assertEqual(self.client.get(reverse("extraccion_vista", args=[extraccion.pk])).status_code, 200)

    def test_datos_para_los_cuatro_graficos(self):
        from apps.consolidado.servicios import datos_graficos

        datos = datos_graficos(Usuario.objects.get(username="gerente_demo"))
        self.assertGreaterEqual(len(datos["activos_por_persona"]), 3)
        self.assertGreaterEqual(len(datos["cumplidos_por_mes"]), 3)  # varios meses
        self.assertGreaterEqual(len(datos["atencion_por_cliente"]), 3)
        self.assertGreaterEqual(len(datos["observaciones_por_tipo"]), 3)
        self.assertTrue(any(m["porcentaje"] < 100 for m in datos["cumplidos_por_mes"]))  # hay entregas tardías

    def test_reportes_de_avance_automatico_y_a_pedido_con_aviso_al_gerente(self):
        from apps.reportes.models import ConfiguracionReporte, ReporteAvance

        self.assertEqual(set(ReporteAvance.objects.values_list("origen", flat=True)), {"AUTOMATICO", "MANUAL"})
        for reporte in ReporteAvance.objects.all():
            with reporte.archivo.open("rb") as f:
                self.assertTrue(f.read().startswith(b"%PDF"))
        gerente = Usuario.objects.get(username="gerente_demo")
        self.assertEqual(Notificacion.objects.filter(usuario=gerente, tipo="REPORTE").count(), 2)
        self.assertEqual(ConfiguracionReporte.objects.count(), 1)

    def test_el_resumen_orienta_la_demostracion(self):
        salida = self.salida.getvalue()
        for texto in ("Alerta urgente abierta", "Checklists por TDR", "F001-00104", "Exportaciones", "Extracción pendiente", "Reportes:"):
            self.assertIn(texto, salida)

    def test_cada_pantalla_del_sprint_3_responde_con_cada_rol(self):
        """Recorrido con los datos de demostración: nada responde 500 ni falla una plantilla."""
        from apps.reportes.models import ReporteAvance

        entregable = Entregable.objects.exclude(estado=E.HECHO).filter(etiquetas_asignadas__isnull=False).first()
        rutas = [reverse(n) for n in ("inicio", "tablero", "entregables", "etiquetas", "checklists", "calidad", "consolidado",
                                      "reportes", "entregable_nuevo")]
        rutas += [reverse("entregable_detalle", args=[entregable.pk]),
                  reverse("reporte_detalle", args=[ReporteAvance.objects.first().pk])]
        for usuario in ("gerente_demo", "senior1", "junior1"):
            self.client.login(username=usuario, password="demo1234")
            for ruta in rutas:
                r = self.client.get(ruta)
                self.assertIn(r.status_code, (200, 403, 404), f"{usuario} {ruta} -> {r.status_code}")
                if ruta.startswith(("/reportes", "/consolidado")) and usuario != "gerente_demo":
                    self.assertEqual(r.status_code, 403, f"{usuario} {ruta}")
                elif usuario == "gerente_demo":
                    self.assertEqual(r.status_code, 200, f"{usuario} {ruta}")
            self.client.logout()


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
        from apps.levantamiento.models import FichaLevantamiento
        from apps.repositorio.models import VersionDocumento

        rutas = (
            {a.archivo.path for a in Adjunto.objects.all()}
            | {v.archivo.path for v in VersionDocumento.objects.all()}
            | {f.archivo_tdr.path for f in FichaLevantamiento.objects.all()}
        )
        self.assertTrue(all(os.path.exists(r) for r in rutas))
        with self.captureOnCommitCallbacks(execute=True):  # en pruebas hay que forzar lo que ocurre al confirmar
            self.sembrar("--reset")
        self.assertEqual(Entregable.objects.count(), 30)
        self.assertFalse(any(os.path.exists(r) for r in rutas))  # no quedan huérfanos de la siembra anterior
        self.assertEqual(Adjunto.objects.count(), len({a.archivo.path for a in Adjunto.objects.all()}))

    def test_reset_sin_datos_previos_funciona(self):
        self.sembrar("--reset")
        self.assertEqual(Usuario.objects.count(), 7)

    def test_reset_repetido_deja_los_mismos_datos_del_sprint_3_y_sin_archivos_huerfanos(self):
        from apps.extraccion.models import Extraccion
        from apps.facturacion.models import FacturaSimulada
        from apps.reportes.models import ReporteAvance
        from apps.urgencias.models import AlertaUrgente

        def cifras_s3():
            return (FacturaSimulada.objects.count(), AlertaUrgente.objects.count(), ReporteAvance.objects.count(),
                    Extraccion.objects.count(), Adjunto.objects.filter(tipo="EXPORTACION").count(),
                    Usuario.objects.filter(de_guardia=True).count())

        self.sembrar("--reset")
        antes = cifras_s3()
        rutas = {r.archivo.path for r in ReporteAvance.objects.all()} | {x.archivo.path for x in Extraccion.objects.all()}
        with self.captureOnCommitCallbacks(execute=True):
            self.sembrar("--reset")
        self.assertEqual(cifras_s3(), antes)
        self.assertEqual(antes, (6, 2, 2, 1, 2, 1))
        self.assertFalse(any(os.path.exists(r) for r in rutas))
