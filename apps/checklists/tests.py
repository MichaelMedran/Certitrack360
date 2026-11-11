"""SDD del Sprint 3, hitos S3-H5 (checklist por TDR, RF-44, HU-25) y S3-H6 (checklist de calidad, RF-45, HU-26).

Casos clave de la §13: 34 (el checklist por TDR se genera sin duplicar; enviar con obligatorios pendientes exige
confirmación y queda en el historial) y 35 (no se aprueba sin revisión de calidad conforme del ciclo actual; un No
conforme sin observación se rechaza).
"""
import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.alertas.models import Notificacion
from apps.checklists import calidad, tdr
from apps.checklists.models import ItemCalidad, ItemChecklistTDR, RevisionCalidad
from apps.clientes.models import Cliente, Contrato
from apps.entregables import adjuntos, servicios
from apps.entregables.models import Entregable, Observacion
from apps.entregables.testing import aprobar
from apps.levantamiento import servicios as fichas
from apps.levantamiento.tests import FichaBase

E = Entregable.Estado
I = ItemChecklistTDR
R = RevisionCalidad.Resultado


class ChecklistBase(FichaBase):
    def ficha_confirmada(self):
        ficha = self.crear_ficha_borrador(requerimientos="- Digitalizar expedientes\n2) Reportar avance mensual\n\n")
        self.agregar_item(ficha)
        fichas.confirmar(ficha, self.s1)
        return ficha

    def post(self, usuario, nombre, args, datos=None, **extra):
        self.client.force_login(usuario)
        return self.client.post(reverse(nombre, args=args), datos or {}, **extra)


# ====================================================================== checklist por TDR (HU-25)

class GeneracionTests(ChecklistBase):
    """HU-25 criterio 1: se genera desde la ficha del TDR, un ítem por requisito, documento o formato; admite manuales."""

    def test_los_entregables_generados_por_la_ficha_reciben_su_checklist(self):
        ficha = self.ficha_confirmada()
        generados = list(Entregable.objects.filter(items_ficha__ficha=ficha))
        self.assertEqual(len(generados), 3)
        for e in generados:
            items = [(i.tipo, i.texto, i.obligatorio, i.origen) for i in e.checklist_tdr.all()]
            self.assertEqual(items, [
                ("REQUISITO", "Digitalizar expedientes", True, "FICHA"),
                ("REQUISITO", "Reportar avance mensual", True, "FICHA"),
                ("DOCUMENTO", "Contrato firmado, TDR, cronograma", True, "FICHA"),
                ("DOCUMENTO", "Carta de designación del cliente", True, "FICHA"),
                ("FORMATO", "Reporte mensual en PDF", False, "FICHA"),
                ("FORMATO", "matriz en Excel", False, "FICHA"),
                ("FORMATO", "PDF firmado", False, "FICHA"),
            ])

    def test_generar_a_pedido_no_duplica(self):
        self.ficha_confirmada()
        self.assertEqual(len(tdr.generar(self.e1, self.j1)), 7)  # e1 es del mismo contrato, creado a mano
        self.assertEqual(tdr.generar(self.e1, self.j1), [])
        self.assertEqual(self.e1.checklist_tdr.count(), 7)
        self.assertTrue(self.e1.historial.filter(detalle__startswith="Generó el checklist por TDR").exists())

    def test_sin_ficha_confirmada_no_se_genera_y_lo_dice(self):
        with self.assertRaisesMessage(ValidationError, "no tiene una ficha de levantamiento confirmada"):
            tdr.generar(self.e1, self.j1)

    def test_agregar_a_mano_valida_y_no_repite(self):
        item = tdr.agregar(self.e1, self.j1, "  Certificación ISO vigente ", "DOCUMENTO", True)
        self.assertEqual((item.texto, item.tipo, item.obligatorio, item.origen, item.creado_por),
                         ("Certificación ISO vigente", "DOCUMENTO", True, "MANUAL", self.j1))
        for texto, tipo in (("", "DOCUMENTO"), ("certificación iso vigente", "DOCUMENTO"), ("Otro", "NADA")):
            with self.assertRaises(ValidationError):
                tdr.agregar(self.e1, self.j1, texto, tipo)


class MarcadoTests(ChecklistBase):
    """HU-25 criterio 2: Pendiente, En revisión o Cumplido, con quién y cuándo, y el documento que lo sustenta."""

    def setUp(self):
        self.item = tdr.agregar(self.e1, self.j1, "Certificación ISO vigente", "DOCUMENTO", True)

    def test_marcar_guarda_quien_y_cuando_y_el_sustento(self):
        a = adjuntos.subir(self.e1, self.j1, SimpleUploadedFile("iso.pdf", b"%PDF"), "EVIDENCIA")
        tdr.marcar(self.item, self.j1, I.Estado.CUMPLIDO, a.pk)
        self.item.refresh_from_db()
        self.assertEqual((self.item.estado, self.item.marcado_por, self.item.adjunto), ("CUMPLIDO", self.j1, a))
        self.assertIsNotNone(self.item.marcado_en)
        tdr.marcar(self.item, self.s1, I.Estado.EN_REVISION)
        self.item.refresh_from_db()
        self.assertEqual((self.item.estado, self.item.marcado_por, self.item.adjunto), ("EN_REVISION", self.s1, None))

    def test_el_sustento_debe_ser_del_mismo_entregable_y_el_estado_valido(self):
        ajeno = adjuntos.subir(self.e2, self.j2, SimpleUploadedFile("otro.pdf", b"%PDF"), "EVIDENCIA")
        for estado, adjunto in ((I.Estado.CUMPLIDO, ajeno.pk), (I.Estado.CUMPLIDO, "abc"), ("LISTO", None)):
            with self.assertRaises(ValidationError):
                tdr.marcar(self.item, self.j1, estado, adjunto)
        self.item.refresh_from_db()
        self.assertEqual(self.item.estado, "PENDIENTE")

    def test_solo_los_responsables_y_no_en_un_entregado(self):
        with self.assertRaises(PermissionDenied):
            tdr.marcar(self.item, self.j2, I.Estado.CUMPLIDO)
        Entregable.objects.filter(pk=self.e1.pk).update(estado=E.HECHO)
        self.item.entregable.refresh_from_db()
        with self.assertRaises(ValidationError):
            tdr.marcar(self.item, self.j1, I.Estado.CUMPLIDO)

    def test_vista_404_si_no_lo_ve_y_403_si_no_es_responsable(self):
        datos = {"accion": "marcar", "item": self.item.pk, "estado": "CUMPLIDO"}
        self.assertEqual(self.post(self.j2, "entregable_checklist", [self.e1.pk], datos).status_code, 404)
        Entregable.objects.filter(pk=self.e1.pk).update(estado=E.HECHO)
        self.assertEqual(self.post(self.j1, "entregable_checklist", [self.e1.pk], datos).status_code, 403)

    def test_vista_marca_agrega_y_genera(self):
        r = self.post(self.j1, "entregable_checklist", [self.e1.pk],
                      {"accion": "marcar", "item": self.item.pk, "estado": "CUMPLIDO"})
        self.assertRedirects(r, reverse("entregable_detalle", args=[self.e1.pk]) + "#checklist-tdr",
                             fetch_redirect_response=False)
        self.item.refresh_from_db()
        self.assertEqual(self.item.estado, "CUMPLIDO")
        self.post(self.j1, "entregable_checklist", [self.e1.pk],
                  {"accion": "agregar", "texto": "Formato F-01", "tipo": "FORMATO"})
        self.assertTrue(self.e1.checklist_tdr.filter(texto="Formato F-01", obligatorio=False).exists())
        r = self.post(self.j1, "entregable_checklist", [self.e1.pk], {"accion": "generar"}, follow=True)
        self.assertContains(r, "no tiene una ficha de levantamiento confirmada")
        # un ítem de otro entregable no existe para este
        ajeno = tdr.agregar(self.e2, self.j2, "X", "REQUISITO")
        r = self.post(self.j1, "entregable_checklist", [self.e1.pk], {"accion": "marcar", "item": ajeno.pk, "estado": "CUMPLIDO"})
        self.assertEqual(r.status_code, 404)


class CumplimientoTests(ChecklistBase):
    """HU-25 criterio 3: porcentaje de cumplimiento y obligatorios pendientes resaltados."""

    def test_porcentaje_y_pendientes_en_el_detalle(self):
        a = tdr.agregar(self.e1, self.j1, "Requisito A", "REQUISITO", True)
        tdr.agregar(self.e1, self.j1, "Requisito B", "REQUISITO", True)
        tdr.agregar(self.e1, self.j1, "Formato C", "FORMATO", False)
        tdr.marcar(a, self.j1, I.Estado.CUMPLIDO)
        datos = tdr.resumen(self.e1)
        self.assertEqual((datos["total"], datos["cumplidos"], datos["porcentaje"]), (3, 1, 33))
        self.assertEqual([i.texto for i in datos["obligatorios_pendientes"]], ["Requisito B"])
        self.client.force_login(self.j1)
        html = self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).content.decode()
        self.assertIn("33 % de cumplimiento", html)
        self.assertIn("1 ítem obligatorio sin cumplir", html)
        self.assertIn("Obligatorio pendiente", html)

    def test_quien_solo_lo_ve_no_tiene_formularios(self):
        tdr.agregar(self.e1, self.j1, "Requisito A", "REQUISITO", True)
        Entregable.objects.filter(pk=self.e1.pk).update(estado=E.HECHO)
        self.client.force_login(self.j1)
        html = self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).content.decode()
        self.assertIn("Requisito A", html)
        self.assertNotIn(reverse("entregable_checklist", args=[self.e1.pk]), html)


class Caso34AvisoAntesDeRevisionTests(ChecklistBase):
    """HU-25 criterio 4 y caso 34: con obligatorios pendientes se advierte antes de enviar a Revisión senior."""

    def setUp(self):
        self.proc = self.nuevo(self.c1, self.j1, self.s1, "En proceso", E.EN_PROCESO)
        self.item = tdr.agregar(self.proc, self.j1, "Certificación ISO vigente", "DOCUMENTO", True)

    def test_mover_pide_confirmacion_y_no_cambia_el_estado(self):
        with self.assertRaises(ValidationError) as ctx:
            servicios.mover(self.proc, E.VERIFICACION_SENIOR, self.j1)
        self.assertEqual(ctx.exception.code, "advertencia")
        self.assertEqual(ctx.exception.params["clave"], tdr.CLAVE_ADVERTENCIA)
        self.assertIn("1 ítem obligatorio sin cumplir («Certificación ISO vigente»)", ctx.exception.params["mensaje"])
        self.assertEqual(Entregable.objects.get(pk=self.proc.pk).estado, E.EN_PROCESO)

    def test_confirmado_se_envia_y_queda_en_el_historial(self):
        servicios.mover(self.proc, E.VERIFICACION_SENIOR, self.j1, confirmadas=[tdr.CLAVE_ADVERTENCIA])
        self.assertEqual(Entregable.objects.get(pk=self.proc.pk).estado, E.VERIFICACION_SENIOR)
        self.assertTrue(self.proc.historial.filter(
            detalle="Enviado a revisión con 1 ítem obligatorio del checklist por TDR pendiente", usuario=self.j1).exists())

    def test_sin_obligatorios_pendientes_no_hay_aviso_ni_registro(self):
        tdr.marcar(self.item, self.j1, I.Estado.CUMPLIDO)
        tdr.agregar(self.proc, self.j1, "Formato opcional", "FORMATO", False)
        servicios.mover(self.proc, E.VERIFICACION_SENIOR, self.j1)
        self.assertFalse(self.proc.historial.filter(detalle__startswith="Enviado a revisión con").exists())

    def test_un_bloqueo_real_gana_a_la_advertencia(self):
        Observacion.objects.create(entregable=self.proc, autor=self.s1, tipo_error="FORMATO", descripcion="x")
        with self.assertRaises(ValidationError) as ctx:
            servicios.mover(self.proc, E.VERIFICACION_SENIOR, self.j1, confirmadas=[tdr.CLAVE_ADVERTENCIA])
        self.assertNotEqual(getattr(ctx.exception, "code", None), "advertencia")

    def test_detalle_muestra_el_aviso_y_continuar_de_todos_modos(self):
        r = self.post(self.j1, "entregable_estado", [self.proc.pk], {"estado": E.VERIFICACION_SENIOR})
        self.assertEqual(r.status_code, 422)
        self.assertContains(r, "Continuar de todos modos", status_code=422)
        self.assertContains(r, f'name="confirmar" value="{tdr.CLAVE_ADVERTENCIA}"', status_code=422)
        r = self.post(self.j1, "entregable_estado", [self.proc.pk],
                      {"estado": E.VERIFICACION_SENIOR, "confirmar": tdr.CLAVE_ADVERTENCIA})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Entregable.objects.get(pk=self.proc.pk).estado, E.VERIFICACION_SENIOR)

    def test_tablero_responde_422_y_pide_confirmar_sin_mostrar_error(self):
        r = self.post(self.j1, "entregable_estado", [self.proc.pk], {"estado": E.VERIFICACION_SENIOR}, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 422)
        evento = json.loads(r["HX-Trigger"])["confirmarAdvertencia"]
        self.assertEqual((evento["id"], evento["estado"], evento["clave"]),
                         (self.proc.pk, E.VERIFICACION_SENIOR, tdr.CLAVE_ADVERTENCIA))
        self.assertNotContains(r, "aviso-error", status_code=422)
        r = self.post(self.j1, "entregable_estado", [self.proc.pk],
                      {"estado": E.VERIFICACION_SENIOR, "confirmar": tdr.CLAVE_ADVERTENCIA}, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)


class ConsultaTests(ChecklistBase):
    """HU-25 criterio 5: se consulta y se filtra por cliente y por contrato o TDR, sin ampliar la visibilidad."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Entregable.objects.filter(pk=cls.e1.pk).update(id_tdr="TDR-UNO")
        Entregable.objects.filter(pk=cls.e2.pk).update(id_tdr="TDR-DOS")
        a = tdr.agregar(cls.e1, cls.j1, "Requisito A", "REQUISITO", True)
        tdr.agregar(cls.e1, cls.j1, "Requisito B", "REQUISITO", True)
        tdr.marcar(a, cls.j1, I.Estado.CUMPLIDO)
        tdr.agregar(cls.e2, cls.j2, "Requisito C", "REQUISITO", True)

    def filas(self, usuario, **params):
        self.client.force_login(usuario)
        r = self.client.get(reverse("checklists"), params)
        self.assertEqual(r.status_code, 200)
        return r

    def test_cada_rol_ve_solo_lo_suyo_con_su_porcentaje(self):
        r = self.filas(self.j1)
        self.assertEqual([(e.pk, e.porcentaje, e.n_obligatorios_pendientes) for e in r.context["filas"]], [(self.e1.pk, 50, 1)])
        self.assertContains(r, "50 %")
        self.assertEqual({e.pk for e in self.filas(self.gerente).context["filas"]}, {self.e1.pk, self.e2.pk})

    def test_filtros_por_cliente_contrato_e_id_tdr(self):
        otro = Cliente.objects.create(nombre="Otro cliente", sector="BANCA")
        Contrato.objects.filter(pk=self.c2.pk).update(cliente=otro)
        self.assertEqual([e.pk for e in self.filas(self.gerente, cliente=otro.pk).context["filas"]], [self.e2.pk])
        self.assertEqual([e.pk for e in self.filas(self.gerente, contrato=self.c1.pk).context["filas"]], [self.e1.pk])
        r = self.filas(self.gerente, id_tdr="tdr-dos")
        self.assertEqual([e.pk for e in r.context["filas"]], [self.e2.pk])
        self.assertEqual([c["texto"] for c in r.context["chips"]], ["ID-TDR: tdr-dos"])
        # un filtro no amplía la visibilidad
        self.assertEqual(self.filas(self.j1, contrato=self.c2.pk).context["filas"], [])

    def test_es_una_pestana_de_entregables_y_htmx_recibe_solo_la_lista(self):
        r = self.filas(self.j1)
        self.assertContains(r, 'aria-current="true">Checklists</a>')
        self.client.force_login(self.j1)
        parcial = self.client.get(reverse("checklists"), HTTP_HX_REQUEST="true").content.decode()
        self.assertNotIn("<h1>", parcial)
        self.assertIn(self.e1.codigo, parcial)


# ====================================================================== checklist de calidad (HU-26)

class CalidadBase(ChecklistBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.rev = cls.nuevo(cls.c1, cls.j1, cls.s1, "En revisión", E.VERIFICACION_SENIOR)
        cls.generales = list(ItemCalidad.objects.filter(cliente__isnull=True).order_by("orden"))

    def conformes(self, **cambios):
        respuestas = {i.pk: (R.CONFORME, "") for i in calidad.items_aplicables(self.rev)}
        respuestas.update(cambios)
        return respuestas


class ConfiguracionTests(CalidadBase):
    """HU-26 criterios 1 y 2: ítems mínimos y configuración por cliente a cargo del senior."""

    def test_los_cuatro_items_minimos_existen_y_son_obligatorios(self):
        self.assertEqual([i.categoria for i in self.generales],
                         ["INFORMACION_COMPLETA", "CONSISTENCIA", "FECHAS_VIGENCIA", "FORMATO"])
        self.assertTrue(all(i.obligatorio and i.activo for i in self.generales))

    def test_al_entregable_le_aplican_los_generales_y_los_de_su_cliente(self):
        propio = calidad.guardar_item(self.s1, cliente=self.cliente, texto="Sello del banco en cada hoja", categoria="FORMATO")
        otro = Cliente.objects.create(nombre="Otro", sector="BANCA")
        calidad.guardar_item(self.gerente, cliente=otro, texto="Solo del otro cliente", categoria="OTRO")
        calidad.guardar_item(self.gerente, propio, texto="Sello del banco", categoria="FORMATO", obligatorio=False)
        textos = [i.texto for i in calidad.items_aplicables(self.rev)]
        self.assertEqual(textos, [i.texto for i in self.generales] + ["Sello del banco"])
        calidad.guardar_item(self.gerente, propio, texto="Sello del banco", categoria="FORMATO", activo=False)
        self.assertNotIn("Sello del banco", [i.texto for i in calidad.items_aplicables(self.rev)])

    def test_el_senior_configura_sus_clientes_pero_no_los_generales_ni_los_ajenos(self):
        otro = Cliente.objects.create(nombre="Otro", sector="BANCA")
        for cliente in (None, otro):
            with self.assertRaises(PermissionDenied):
                calidad.guardar_item(self.s1, cliente=cliente, texto="x", categoria="OTRO")
        with self.assertRaises(PermissionDenied):
            calidad.guardar_item(self.s1, self.generales[0], texto="cambiado", categoria="OTRO")
        with self.assertRaises(PermissionDenied):
            calidad.guardar_item(self.j1, cliente=self.cliente, texto="x", categoria="OTRO")
        with self.assertRaises(ValidationError):
            calidad.guardar_item(self.s1, cliente=self.cliente, texto="  ", categoria="OTRO")

    def test_pantalla_por_rol(self):
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(reverse("calidad")).status_code, 403)
        self.client.force_login(self.s1)
        r = self.client.get(reverse("calidad"))
        self.assertNotContains(r, 'aria-label="Gestión"')
        self.assertNotContains(r, "Todos los clientes (general)")
        self.assertEqual(self.client.get(reverse("calidad"), {"editar": self.generales[0].pk}).status_code, 403)
        r = self.client.post(reverse("calidad"), {"cliente": self.cliente.pk, "texto": "Firma del supervisor",
                                                  "categoria": "FORMATO", "obligatorio": "on", "activo": "on"})
        self.assertRedirects(r, reverse("calidad"))
        self.assertTrue(ItemCalidad.objects.filter(cliente=self.cliente, texto="Firma del supervisor").exists())
        self.assertEqual(self.client.post(reverse("calidad"), {"texto": "General", "categoria": "OTRO"}).status_code, 403)
        self.client.force_login(self.gerente)
        r = self.client.get(reverse("calidad"))
        self.assertContains(r, 'aria-current="page">Checklist de calidad</a>')
        self.client.post(reverse("calidad"), {"texto": "General nuevo", "categoria": "OTRO", "activo": "on"})
        self.assertTrue(ItemCalidad.objects.filter(cliente__isnull=True, texto="General nuevo", obligatorio=False).exists())


class Caso35RevisionTests(CalidadBase):
    """HU-26 criterios 3, 4 y 5 y caso 35."""

    def test_sin_revision_conforme_no_se_aprueba(self):
        with self.assertRaisesMessage(ValidationError, "falta el checklist de control de calidad"):
            servicios.mover(self.rev, E.LISTO_PARA_ENTREGA, self.s1)
        self.assertEqual(Entregable.objects.get(pk=self.rev.pk).estado, E.VERIFICACION_SENIOR)

    def test_con_todos_los_obligatorios_conformes_se_aprueba_y_queda_registrada(self):
        revision, devuelto = calidad.registrar(self.rev, self.s1, self.conformes())
        self.assertEqual((revision.resultado, revision.revisor, devuelto), (R.CONFORME, self.s1, False))
        self.assertIsNotNone(revision.fecha)
        self.assertEqual(revision.respuestas.count(), 4)
        servicios.mover(self.rev, E.LISTO_PARA_ENTREGA, self.s1)
        self.assertEqual(Entregable.objects.get(pk=self.rev.pk).estado, E.LISTO_PARA_ENTREGA)

    def test_no_conforme_exige_observacion_y_todos_los_items_respondidos(self):
        item = self.generales[0]
        with self.assertRaisesMessage(ValidationError, "registre la observación"):
            sin_texto = self.conformes()
            sin_texto[item.pk] = (R.NO_CONFORME, "  ")
            calidad.registrar(self.rev, self.s1, sin_texto)
        incompletas = self.conformes()
        del incompletas[item.pk]
        with self.assertRaisesMessage(ValidationError, "como Conforme o No conforme"):
            calidad.registrar(self.rev, self.s1, incompletas)
        self.assertFalse(RevisionCalidad.objects.exists())

    def test_no_conforme_registra_la_observacion_devuelve_y_avisa(self):
        item = self.generales[3]  # formato
        respuestas = self.conformes()
        respuestas[item.pk] = (R.NO_CONFORME, "Falta el membrete del cliente")
        revision, devuelto = calidad.registrar(self.rev, self.s1, respuestas)
        self.assertEqual((revision.resultado, devuelto), (R.NO_CONFORME, True))
        e = Entregable.objects.get(pk=self.rev.pk)
        self.assertEqual(e.estado, E.EN_PROCESO)
        obs = e.observaciones.get()
        self.assertEqual((obs.tipo_error, obs.estado, obs.autor), ("FORMATO", "PENDIENTE", self.s1))
        self.assertIn("Falta el membrete del cliente", obs.descripcion)
        self.assertTrue(Notificacion.objects.filter(usuario=self.j1, entregable=e, tipo="OBSERVACION").exists())
        self.client.force_login(self.j1)
        self.assertContains(self.client.get(reverse("entregable_detalle", args=[e.pk])), "Con correcciones pendientes")

    def test_la_revision_de_un_ciclo_anterior_no_sirve_para_aprobar(self):
        proc = self.nuevo(self.c1, self.j1, self.s1, "Ciclos", E.EN_PROCESO)
        servicios.mover(proc, E.VERIFICACION_SENIOR, self.j1)
        self.assertIsNotNone(calidad.registrar_conforme(proc, self.s1))
        servicios.mover(proc, E.EN_PROCESO, self.s1, tipo_error="FORMATO", descripcion="Otra cosa")  # devuelto
        obs = proc.observaciones.get()
        from apps.entregables import observaciones as obs_servicio
        obs_servicio.corregir(obs, self.j1, "Corregido")
        servicios.mover(proc, E.VERIFICACION_SENIOR, self.j1)
        obs_servicio.confirmar(obs, self.s1)
        self.assertIsNone(calidad.revision_vigente(proc))
        with self.assertRaisesMessage(ValidationError, "falta el checklist de control de calidad"):
            servicios.mover(proc, E.LISTO_PARA_ENTREGA, self.s1)
        aprobar(proc, self.s1)
        self.assertEqual(proc.estado, E.LISTO_PARA_ENTREGA)
        self.assertEqual(proc.revisiones_calidad.count(), 2)

    def test_un_no_obligatorio_no_conforme_da_conforme_pero_genera_su_observacion(self):
        opcional = calidad.guardar_item(self.s1, cliente=self.cliente, texto="Índice paginado", categoria="FORMATO",
                                        obligatorio=False)
        respuestas = self.conformes()
        respuestas[opcional.pk] = (R.NO_CONFORME, "Sin índice")
        revision, devuelto = calidad.registrar(self.rev, self.s1, respuestas)
        self.assertEqual((revision.resultado, devuelto), (R.CONFORME, True))

    def test_solo_el_senior_del_entregable_y_solo_en_revision(self):
        for usuario in (self.j1, self.s2):
            with self.assertRaises(PermissionDenied):
                calidad.registrar(self.rev, usuario, self.conformes())
        with self.assertRaisesMessage(ValidationError, "se aplica cuando el entregable está en"):
            calidad.registrar(self.e1, self.s1, {})

    def test_sin_items_aplicables_se_aprueba_sin_checklist(self):
        ItemCalidad.objects.update(activo=False)
        servicios.mover(self.rev, E.LISTO_PARA_ENTREGA, self.s1)
        self.assertEqual(Entregable.objects.get(pk=self.rev.pk).estado, E.LISTO_PARA_ENTREGA)

    def test_la_revision_guarda_el_texto_aunque_el_item_cambie(self):
        revision, _ = calidad.registrar(self.rev, self.s1, self.conformes())
        original = self.generales[0].texto
        calidad.guardar_item(self.gerente, self.generales[0], texto="Texto nuevo", categoria="OTRO")
        self.assertEqual(revision.respuestas.order_by("id").first().texto, original)


class PantallaDeCalidadTests(CalidadBase):
    def test_el_checklist_aparece_en_revision_senior_con_formulario_solo_para_el_senior(self):
        url = reverse("entregable_detalle", args=[self.rev.pk])
        self.client.force_login(self.s1)
        html = self.client.get(url).content.decode()
        self.assertIn('id="checklist-calidad"', html)
        self.assertIn(reverse("entregable_calidad", args=[self.rev.pk]), html)
        for item in self.generales:
            self.assertIn(f'name="r_{item.pk}"', html)
        self.client.force_login(self.j1)
        html = self.client.get(url).content.decode()
        self.assertIn(self.generales[0].texto, html)
        self.assertNotIn(reverse("entregable_calidad", args=[self.rev.pk]), html)
        # fuera de Revisión senior y sin revisiones, la sección no aparece
        self.assertNotContains(self.client.get(reverse("entregable_detalle", args=[self.e1.pk])), 'id="checklist-calidad"')

    def test_vista_registra_y_muestra_el_historial_de_revisiones(self):
        datos = {f"r_{i.pk}": R.CONFORME for i in self.generales}
        r = self.post(self.s1, "entregable_calidad", [self.rev.pk], datos, follow=True)
        self.assertContains(r, "Revisión de calidad conforme: el entregable ya se puede aprobar.")
        self.assertContains(r, "Revisiones de calidad")
        self.assertContains(r, self.s1.nombre)
        item = self.generales[1]
        otro = self.nuevo(self.c1, self.j1, self.s1, "Otro en revisión", E.VERIFICACION_SENIOR)
        datos[f"r_{item.pk}"] = R.NO_CONFORME
        r = self.post(self.s1, "entregable_calidad", [otro.pk], datos, follow=True)
        self.assertContains(r, "registre la observación")
        datos[f"o_{item.pk}"] = "Los totales no cuadran"
        r = self.post(self.s1, "entregable_calidad", [otro.pk], datos, follow=True)
        self.assertContains(r, "volvió a «En proceso»")
        self.assertContains(r, "Los totales no cuadran")

    def test_vista_404_y_403(self):
        self.assertEqual(self.post(self.j2, "entregable_calidad", [self.rev.pk]).status_code, 404)
        self.assertEqual(self.post(self.j1, "entregable_calidad", [self.rev.pk]).status_code, 403)

    def test_el_detalle_dice_que_falta_la_revision_al_intentar_aprobar(self):
        r = self.post(self.s1, "entregable_estado", [self.rev.pk], {"estado": E.LISTO_PARA_ENTREGA}, follow=True)
        self.assertContains(r, "falta el checklist de control de calidad")
