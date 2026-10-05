"""Pruebas de la interfaz: tablero, lista, mover con HTMX, detalle con adjuntos y Nuevo entregable (SDD §12.3, §13)."""
import json
import re

from django.core.files.base import ContentFile
from django.urls import reverse

from apps.alertas.models import Notificacion
from apps.clientes.models import PlantillaTDR
from apps.entregables import adjuntos
from apps.entregables.models import Entregable, Observacion
from apps.entregables.test_filtros import FiltrosBase
from apps.entregables.tests import Base

E = Entregable.Estado
HX = {"HTTP_HX_REQUEST": "true"}


def tarjetas(html):
    return re.findall(r'<article class="ficha[^"]*"[^>]*>.*?</article>', html, flags=re.S)


def tarjeta_de(html, titulo):
    return next(t for t in tarjetas(html) if f">{titulo}</a>" in t)


def columnas(respuesta):
    return {c["valor"]: [e.titulo for e in c["tarjetas"]] for c in respuesta.context["columnas"]}


class TableroTests(FiltrosBase):
    def ver(self, usuario, params=None, **extra):
        self.client.force_login(usuario)
        return self.client.get(reverse("tablero"), params or {}, **extra)

    def test_pagina_completa_con_panel_de_filtros_columnas_y_tarjetas(self):
        r = self.ver(self.gerente)
        html = r.content.decode()
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "<summary>Filtros")
        self.assertContains(r, "0 activos")
        for etiqueta in ("A realizar", "En proceso", "Verificación senior", "Listo para entrega", "Hecho"):
            self.assertContains(r, etiqueta)
        self.assertEqual(len(tarjetas(html)), 9)
        self.assertEqual(html.count("<html"), 1)

    def test_cada_tarjeta_muestra_cliente_contrato_plazo_y_responsable(self):
        html = self.ver(self.gerente).content.decode()
        t = tarjeta_de(html, "a-vencido")
        self.assertIn("Cliente Demo · C1", t)
        self.assertIn(f"Plazo: {self.a.plazo:%d/%m/%Y}", t)
        self.assertIn("j1", t)  # el junior responsable

    def test_la_urgencia_va_en_texto_y_los_hechos_no_la_llevan(self):
        html = self.ver(self.gerente).content.decode()
        self.assertIn(">Vencido</span>", tarjeta_de(html, "a-vencido"))
        self.assertIn(">Crítico</span>", tarjeta_de(html, "c-critico"))
        self.assertIn(">Próximo</span>", tarjeta_de(html, "d-proximo"))
        self.assertIn(">Normal</span>", tarjeta_de(html, "E1"))
        self.assertNotIn('class="urgencia', tarjeta_de(html, "g-hecho"))
        self.assertIn("nivel-vencido", tarjeta_de(html, "a-vencido"))  # marca adicional: no solo color

    def test_contadores_de_observaciones_abiertas_y_adjuntos(self):
        adjuntos.crear_adjunto(self.a, self.s1, ContentFile(b"x", name="a.txt"), "OTRO")
        html = self.ver(self.gerente).content.decode()
        self.assertIn("1 observación abierta: Formato", tarjeta_de(html, "a-vencido"))
        self.assertIn("Adjuntos: 1", tarjeta_de(html, "a-vencido"))
        self.assertIn("1 observación abierta: Contenido", tarjeta_de(html, "d-proximo"))  # la de formato está resuelta
        self.assertNotIn("observación abierta", tarjeta_de(html, "b-hoy"))
        self.assertIn("Adjuntos: 0", tarjeta_de(html, "E1"))

    def test_varias_observaciones_abiertas_se_cuentan_en_plural(self):
        Observacion.objects.create(entregable=self.a, autor=self.s1, tipo_error="CONTENIDO", descripcion="x")
        html = self.ver(self.gerente).content.decode()
        self.assertIn("2 observaciones abiertas: Formato, Contenido", tarjeta_de(html, "a-vencido"))

    def test_htmx_recibe_solo_el_fragmento_con_el_resumen_de_filtros(self):
        r = self.ver(self.gerente, {"urgencia": "VENCIDO"}, **HX)
        html = r.content.decode()
        self.assertNotIn("<html", html)
        self.assertNotIn("<header", html)
        self.assertIn('class="tablero"', html)
        self.assertEqual(len(tarjetas(html)), 2)
        self.assertIn('id="resumen-filtros" hx-swap-oob="true">1 activo<', html)
        self.assertIn("HX-Request", r["Vary"])

    def test_al_restaurar_el_historial_se_responde_la_pagina_completa(self):
        r = self.ver(self.gerente, HTTP_HX_REQUEST="true", HTTP_HX_HISTORY_RESTORE_REQUEST="true")
        self.assertIn("<html", r.content.decode())

    def test_chips_con_el_enlace_que_quita_cada_filtro(self):
        r = self.ver(self.gerente, {"urgencia": "VENCIDO", "cliente": self.cliente.pk, "orden": "urgencia"})
        chips = {c["clave"]: c for c in r.context["chips"]}
        self.assertEqual(set(chips), {"urgencia", "cliente"})
        self.assertEqual(chips["urgencia"]["texto"], "Urgencia: Vencido")
        self.assertEqual(chips["cliente"]["texto"], "Cliente: Cliente Demo")
        self.assertNotIn("urgencia=", chips["urgencia"]["quitar"])
        self.assertIn("cliente=", chips["urgencia"]["quitar"])
        self.assertIn("orden=urgencia", chips["cliente"]["quitar"])  # el orden se conserva
        self.assertContains(r, "2 activos")

    def test_el_chip_de_un_filtro_que_no_corresponde_no_revela_nada(self):
        self.client.force_login(self.j1)
        r = self.client.get(reverse("tablero"), {"contrato": self.c2.pk})  # C2 no es de j1: no lo ve ni filtrando por él
        self.assertEqual(sum(len(v) for v in columnas(r).values()), 0)
        self.assertContains(r, "No hay entregables con estos filtros.")
        self.assertNotContains(r, "C2 ·")  # ni su número aparece entre las opciones o los chips
        self.assertNotContains(r, "Contrato: C2")

    def test_cada_rol_ve_solo_lo_suyo(self):
        self.assertEqual({t for v in columnas(self.ver(self.j1)).values() for t in v}, {"E1", "a-vencido", "b-hoy", "c-critico", "g-hecho"})
        self.assertEqual({t for v in columnas(self.ver(self.s2)).values() for t in v}, {"E2", "f-proximo", "h-vencido"})

    def test_las_opciones_del_panel_solo_ofrecen_lo_visible(self):
        html = self.ver(self.j2).content.decode()
        self.assertNotIn(">j1<", html)
        self.assertIn("Segundo Cliente", html)  # j2 tiene un entregable en C3
        html1 = self.ver(self.j1).content.decode()
        self.assertNotIn("C2 ·", html1)

    def test_el_orden_se_aplica_dentro_de_cada_columna(self):
        r = self.ver(self.gerente, {"orden": "urgencia"})
        self.assertEqual(columnas(r)["EN_PROCESO"], ["a-vencido", "h-vencido", "b-hoy", "c-critico"])

    def test_el_dialogo_de_devolucion_trae_tipos_y_campos_obligatorios(self):
        html = self.ver(self.s1).content.decode()
        self.assertIn('<dialog id="dialogo-devolver"', html)
        self.assertIn('<select id="d-tipo" required>', html)
        self.assertIn('<textarea id="d-desc" rows="3" required>', html)
        for valor in ("DATO_FALTANTE", "FORMATO", "PLAZO", "CONTENIDO", "OTRO"):
            self.assertIn(f'<option value="{valor}">', html)

    def test_la_pagina_apunta_al_endpoint_de_mover_y_lleva_el_token(self):
        html = self.ver(self.s1).content.decode()
        self.assertIn(f'data-mover-url="{reverse("entregable_estado", args=[0])}"', html)
        self.assertRegex(html, r'data-csrf="[A-Za-z0-9]{32,}"')
        self.assertIn("hx-headers=", html)

    def test_las_paginas_privadas_no_se_cachean(self):
        r = self.ver(self.gerente)
        self.assertIn("no-store", r["Cache-Control"])

    def test_el_teclado_tiene_una_via_alternativa_explicada(self):
        self.assertContains(self.ver(self.j1), "Con el teclado, abra la tarjeta")


class MoverConHtmxTests(Base):
    def mover(self, usuario, entregable, estado, query="", **datos):
        self.client.force_login(usuario)
        return self.client.post(reverse("entregable_estado", args=[entregable.pk]) + query, {"estado": estado, **datos}, **HX)

    def test_un_movimiento_valido_responde_el_tablero_actualizado(self):
        r = self.mover(self.j1, self.e1, "EN_PROCESO")
        self.assertEqual(r.status_code, 200)
        self.assertIn("E1", columnas(r)["EN_PROCESO"])
        self.assertNotIn("E1", columnas(r)["A_REALIZAR"])
        self.assertContains(r, "«E1» pasó a «En proceso».")
        self.assertNotIn("<html", r.content.decode())
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.estado, E.EN_PROCESO)
        self.assertEqual(self.e1.historial.get().usuario, self.j1)

    def test_un_movimiento_no_permitido_da_422_y_la_tarjeta_sigue_en_su_columna(self):
        r = self.mover(self.j1, self.e1, "HECHO")
        self.assertEqual(r.status_code, 422)
        self.assertContains(r, "Ese movimiento no está permitido", status_code=422)
        self.assertIn("E1", columnas(r)["A_REALIZAR"])
        self.assertEqual(self.e1.historial.count(), 0)

    def test_sin_permiso_da_403_con_su_motivo(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "V", E.VERIFICACION_SENIOR)
        r = self.mover(self.j1, e, "LISTO_PARA_ENTREGA")
        self.assertEqual(r.status_code, 403)
        self.assertContains(r, "No tiene permiso", status_code=403)
        e.refresh_from_db()
        self.assertEqual(e.estado, E.VERIFICACION_SENIOR)

    def test_un_entregable_ajeno_es_404(self):
        self.assertEqual(self.mover(self.j1, self.e2, "EN_PROCESO").status_code, 404)

    def test_devolver_sin_observacion_pide_el_dialogo_sin_reprochar_nada(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Informe técnico ñandú", E.VERIFICACION_SENIOR)
        r = self.mover(self.s1, e, "EN_PROCESO")
        self.assertEqual(r.status_code, 422)
        evento = json.loads(r["HX-Trigger"])["pedirObservacion"]
        self.assertEqual(evento, {"id": e.pk, "titulo": "Informe técnico ñandú"})
        self.assertTrue(r["HX-Trigger"].isascii())  # las cabeceras HTTP viajan en ASCII
        self.assertNotContains(r, "aviso-error", status_code=422)
        self.assertIn("Informe técnico ñandú", columnas(r)["VERIFICACION_SENIOR"])

    def test_si_se_envia_una_observacion_incompleta_se_explica(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "V", E.VERIFICACION_SENIOR)
        r = self.mover(self.s1, e, "EN_PROCESO", tipo_error="FORMATO", descripcion="   ")
        self.assertEqual(r.status_code, 422)
        self.assertContains(r, "debe describir la observación", status_code=422)
        self.assertIn("HX-Trigger", r)

    def test_devolver_con_observacion_funciona_y_avisa_al_junior(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "V", E.VERIFICACION_SENIOR)
        r = self.mover(self.s1, e, "EN_PROCESO", tipo_error="FORMATO", descripcion="Falta numeración")
        self.assertEqual(r.status_code, 200)
        self.assertIn("V", columnas(r)["EN_PROCESO"])
        self.assertNotIn("HX-Trigger", r)
        self.assertEqual(e.observaciones.get().tipo_error, "FORMATO")
        self.assertTrue(Notificacion.objects.filter(usuario=self.j1, tipo="OBSERVACION").exists())
        self.assertContains(r, "1 observación abierta: Formato")

    def test_el_tablero_devuelto_respeta_los_filtros_de_la_direccion(self):
        self.nuevo(self.c1, self.j1, self.s1, "vencido", dias=-2)
        r = self.mover(self.s1, self.e1, "EN_PROCESO", query="?urgencia=VENCIDO")
        self.assertEqual(r.status_code, 200)
        self.assertEqual({t for v in columnas(r).values() for t in v}, {"vencido"})  # E1 (normal) ya no está en la vista
        self.assertContains(r, "Urgencia: Vencido")

    def test_las_reglas_de_verificacion_tambien_aplican_por_aqui(self):
        PlantillaTDR.objects.filter(pk=self.plantilla.pk).update(adjuntos_requeridos=["BORRADOR"])
        e = Entregable.objects.get(pk=self.nuevo(self.c1, self.j1, self.s1, "Con adjuntos", E.EN_PROCESO).pk)
        r = self.mover(self.j1, e, "VERIFICACION_SENIOR")
        self.assertEqual(r.status_code, 422)
        self.assertContains(r, "«Borrador»", status_code=422)
        self.assertNotIn("HX-Trigger", r)

    def test_el_formulario_clasico_del_detalle_redirige_con_mensajes(self):
        self.client.force_login(self.j1)
        url = reverse("entregable_estado", args=[self.e1.pk])
        r = self.client.post(url, {"estado": "EN_PROCESO"})
        self.assertRedirects(r, reverse("entregable_detalle", args=[self.e1.pk]))
        r = self.client.post(url, {"estado": "HECHO"}, follow=True)
        self.assertContains(r, "no está permitido")

    def test_solo_post_y_con_sesion(self):
        url = reverse("entregable_estado", args=[self.e1.pk])
        self.assertEqual(self.client.post(url, {"estado": "EN_PROCESO"}, **HX).status_code, 302)
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(url).status_code, 405)


class ListaTests(FiltrosBase):
    def ver(self, usuario, params=None, **extra):
        self.client.force_login(usuario)
        return self.client.get(reverse("entregables"), params or {}, **extra)

    def test_columnas_y_urgencia_en_texto(self):
        html = self.ver(self.gerente).content.decode()
        for cabecera in ("Entregable", "Cliente", "Contrato", "Plazo", "Urgencia", "Estado", "Junior"):
            self.assertIn(f"<th>{cabecera}</th>", html)
        fila = next(f for f in re.findall(r"<tr>.*?</tr>", html, flags=re.S) if "a-vencido" in f)
        self.assertIn(">Vencido</span>", fila)
        hecha = next(f for f in re.findall(r"<tr>.*?</tr>", html, flags=re.S) if "g-hecho" in f)
        self.assertIn("No aplica", hecha)
        self.assertNotIn('class="urgencia', hecha)

    def test_el_boton_nuevo_entregable_depende_del_rol(self):
        for usuario, ve in ((self.gerente, True), (self.s1, True), (self.admin, True), (self.j1, False)):
            with self.subTest(usuario=usuario.username):
                self.assertEqual("Nuevo entregable" in self.ver(usuario).content.decode(), ve)

    def test_htmx_responde_solo_la_tabla_con_su_resumen(self):
        r = self.ver(self.gerente, {"urgencia": "VENCIDO"}, **HX)
        html = r.content.decode()
        self.assertNotIn("<html", html)
        self.assertEqual(html.count("<tr>") - 1, 2)  # 2 filas de datos
        self.assertIn('hx-swap-oob="true">1 activo<', html)

    def test_sin_resultados_lo_dice(self):
        self.assertContains(self.ver(self.gerente, {"tipo_observacion": "PLAZO"}), "No hay entregables para mostrar con estos filtros.")

    def test_el_panel_de_filtros_trae_los_siete_controles_con_etiqueta(self):
        html = self.ver(self.gerente).content.decode()
        for nombre, etiqueta in (("cliente", "Cliente"), ("contrato", "Contrato"), ("responsable", "Responsable"),
                                 ("urgencia", "Urgencia"), ("tipo_observacion", "Tipo de observación abierta"),
                                 ("estado", "Estado"), ("orden", "Ordenar por")):
            self.assertRegex(html, rf'<label for="f-[a-z]+">{etiqueta}</label>\s*<select id="f-[a-z]+" name="{nombre}"')

    def test_el_panel_marca_lo_que_esta_aplicado(self):
        html = self.ver(self.gerente, {"urgencia": "CRITICO", "orden": "cliente"}).content.decode()
        self.assertIn('<option value="CRITICO" selected>', html)
        self.assertIn('<option value="cliente" selected>', html)


class DetalleTests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        PlantillaTDR.objects.filter(pk=cls.plantilla.pk).update(adjuntos_requeridos=["BORRADOR", "EVIDENCIA"])
        cls.e = Entregable.objects.get(pk=cls.nuevo(cls.c1, cls.j1, cls.s1, "Con adjuntos", E.EN_PROCESO).pk)

    def subir(self, tipo, nombre="a.pdf", usuario=None):
        return adjuntos.crear_adjunto(self.e, usuario or self.j1, ContentFile(b"%PDF datos", name=nombre), tipo)

    def ver(self, usuario, entregable=None):
        self.client.force_login(usuario)
        return self.client.get(reverse("entregable_detalle", args=[(entregable or self.e).pk]))

    def test_sin_adjuntos_muestra_lo_que_falta(self):
        r = self.ver(self.j1)
        self.assertContains(r, "Requeridos por la plantilla:")
        self.assertContains(r, "Borrador — falta")
        self.assertContains(r, "Evidencia — falta")
        self.assertContains(r, "Todavía no hay adjuntos.")

    def test_aviso_de_lo_que_falta_para_pasar_a_verificacion(self):
        self.assertContains(self.ver(self.j1), "No se puede enviar a verificación: faltan los adjuntos requeridos («Borrador», «Evidencia»)")
        self.subir("BORRADOR")
        self.subir("EVIDENCIA", "e.png")
        self.assertNotContains(self.ver(self.j1), "No se puede enviar a verificación")

    def test_el_aviso_tambien_nombra_los_datos_faltantes(self):
        e = Entregable.objects.get(pk=self.nuevo(self.c1, self.j1, self.s1, "Sin datos", E.EN_PROCESO).pk)
        e.datos = {"c_periodo": "Enero"}
        e.save()
        self.assertContains(self.ver(self.j1, e), "los datos obligatorios («Nivel»)")

    def test_cumplido_y_ultima_version_de_cada_tipo(self):
        self.subir("BORRADOR")
        self.subir("BORRADOR", "b.pdf")
        r = self.ver(self.j1)
        self.assertContains(r, "Borrador — cumplido")
        self.assertContains(r, "Evidencia — falta")
        grupo = next(g for g in r.context["grupos_adjuntos"] if g["tipo"] == "BORRADOR")
        self.assertEqual((grupo["ultima"].version, [a.version for a in grupo["anteriores"]]), (2, [1]))
        self.assertContains(r, "Ver versiones anteriores de «Borrador» (1)")

    def test_los_tipos_se_ordenan_como_en_el_catalogo(self):
        self.subir("EVIDENCIA", "e.png")
        self.subir("TDR", "t.pdf")
        self.subir("BORRADOR")
        self.assertEqual([g["tipo"] for g in self.ver(self.j1).context["grupos_adjuntos"]], ["TDR", "BORRADOR", "EVIDENCIA"])

    def test_enlaces_de_descarga_por_cada_version(self):
        a1, a2 = self.subir("BORRADOR"), self.subir("BORRADOR", "b.pdf")
        r = self.ver(self.j1)
        for a in (a1, a2):
            self.assertContains(r, reverse("adjunto_descargar", args=[a.pk]))

    def test_eliminar_solo_para_gerente_y_admin(self):
        a = self.subir("BORRADOR")
        for usuario, ve in ((self.gerente, True), (self.admin, True), (self.s1, False), (self.j1, False)):
            with self.subTest(usuario=usuario.username):
                self.assertEqual(reverse("adjunto_eliminar", args=[a.pk]) in self.ver(usuario).content.decode(), ve)
        self.assertContains(self.ver(self.gerente), "no se puede deshacer")  # pide confirmación

    def test_el_formulario_de_subida_depende_del_permiso_y_del_estado(self):
        for usuario in (self.j1, self.s1, self.gerente):
            self.assertContains(self.ver(usuario), "Subir un adjunto")
        enverificacion = Entregable.objects.get(pk=self.nuevo(self.c1, self.j1, self.s1, "En ver", E.VERIFICACION_SENIOR).pk)
        r = self.ver(self.j1, enverificacion)
        self.assertNotContains(r, "Subir un adjunto")
        self.assertContains(r, "Ya no puede subir adjuntos")
        self.assertContains(self.ver(self.s1, enverificacion), "Subir un adjunto")  # el senior sí

    def test_el_formulario_de_subida_dice_los_formatos_y_el_tamano(self):
        r = self.ver(self.j1)
        self.assertContains(r, "Formatos: pdf, docx, xlsx, pptx, png, jpg, txt · máximo 10 MB")
        self.assertContains(r, 'accept=".pdf,.docx,.xlsx,.pptx,.png,.jpg,.txt"')
        self.assertContains(r, 'enctype="multipart/form-data"')
        self.assertContains(r, '<option value="" selected>— Elija el tipo —</option>')

    def test_urgencia_con_texto_y_no_aplica_a_los_hechos(self):
        self.assertContains(self.ver(self.j1), '<span class="urgencia urgencia-normal">Normal</span>')
        hecho = self.nuevo(self.c1, self.j1, self.s1, "Cerrado", E.HECHO)
        r = self.ver(self.j1, hecho)
        self.assertContains(r, "No aplica")
        self.assertNotContains(r, 'class="urgencia')

    def test_el_historial_muestra_subidas_y_cambios_de_estado(self):
        self.subir("BORRADOR")
        r = self.ver(self.j1)
        self.assertContains(r, "Subió adjunto: Borrador v1 (a.pdf)")

    def test_los_dos_formularios_de_observacion_no_repiten_identificadores(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "En ver", E.VERIFICACION_SENIOR)
        html = self.ver(self.s1, e).content.decode()
        ids = re.findall(r'\bid="([^"]+)"', html)
        repetidos = {i for i in ids if ids.count(i) > 1}
        self.assertEqual(repetidos, set())
        for campo in ("dv_tipo_error", "dv_descripcion", "ob_tipo_error", "ob_descripcion"):
            self.assertIn(f'id="{campo}"', html)
            self.assertIn(f'for="{campo}"', html)

    def test_el_boton_de_devolver_pide_los_campos_obligatorios(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "En ver", E.VERIFICACION_SENIOR)
        html = self.ver(self.s1, e).content.decode()
        self.assertIn('<select name="tipo_error" required id="dv_tipo_error">', html)
        self.assertIn("Devolver a «En proceso» (requiere una observación)", html)

    def test_un_entregable_ajeno_sigue_siendo_404(self):
        self.client.force_login(self.j2)
        self.assertEqual(self.client.get(reverse("entregable_detalle", args=[self.e.pk])).status_code, 404)


class NuevoEntregableTests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        PlantillaTDR.objects.filter(pk=cls.plantilla.pk).update(adjuntos_requeridos=["BORRADOR", "TDR"])
        cls.sin_adjuntos = PlantillaTDR.objects.create(nombre="Libre", campos_requeridos=[
            {"nombre": "c_nivel", "etiqueta": "Nivel", "tipo": "opcion", "opciones": ["Alto", "Bajo"]},
            {"nombre": "c_fecha", "etiqueta": "Fecha de reunión", "tipo": "fecha"},
            {"nombre": "c_notas", "etiqueta": "Notas", "tipo": "texto_largo"}])

    def pagina(self, plantilla, usuario=None):
        self.client.force_login(usuario or self.s1)
        return self.client.get(reverse("entregable_nuevo"), {"plantilla": plantilla.pk})

    def datos(self, **extra):
        d = {"plantilla": self.plantilla.pk, "contrato": self.c1.pk, "titulo": "Nuevo", "junior_asignado": self.j1.pk,
             "plazo": (self.hoy + __import__("datetime").timedelta(days=4)).isoformat(), "c_periodo": "Enero", "c_nivel": "2"}
        d.update(extra)
        return d

    def test_informa_los_adjuntos_que_exige_la_plantilla(self):
        self.assertContains(self.pagina(self.plantilla), "Esta plantilla exige estos adjuntos antes de pasar a verificación: <strong>Borrador, TDR</strong>")
        self.assertContains(self.pagina(self.sin_adjuntos), "no exige adjuntos")

    def test_ofrece_elegir_el_senior_revisor(self):
        r = self.pagina(self.plantilla)
        self.assertContains(r, "Senior revisor")
        self.assertContains(r, "— El senior responsable del contrato —")
        self.assertContains(r, "Revisa y aprueba el entregable.")
        opciones = [o.pk for o in r.context["form"].fields["senior_revisor"].queryset]
        self.assertEqual(sorted(opciones), sorted([self.s1.pk, self.s2.pk]))

    def test_los_campos_de_la_plantilla_van_aparte_con_su_tipo(self):
        r = self.pagina(self.sin_adjuntos)
        self.assertContains(r, "<h3>Campos de la plantilla</h3>")
        self.assertContains(r, "Elija una opción")
        self.assertContains(r, "Fecha</span>")
        self.assertContains(r, "Texto largo</span>")
        self.assertEqual([c.label for c in r.context["form"].campos_plantilla], ["Nivel", "Fecha de reunión", "Notas"])
        self.assertEqual([c.name for c in r.context["form"].campos_base],
                         ["contrato", "titulo", "plazo", "junior_asignado", "senior_revisor"])

    def test_todos_los_campos_llevan_etiqueta(self):
        html = self.pagina(self.sin_adjuntos).content.decode()
        for campo in ("id_contrato", "id_titulo", "id_plazo", "id_junior_asignado", "id_senior_revisor", "id_c_nivel", "id_c_fecha", "id_c_notas"):
            self.assertIn(f'<label for="{campo}">', html, campo)

    def test_por_defecto_el_revisor_es_el_responsable_del_contrato(self):
        self.client.force_login(self.s1)
        self.assertEqual(self.client.post(reverse("entregable_nuevo"), self.datos()).status_code, 302)
        self.assertEqual(Entregable.objects.get(titulo="Nuevo").senior_revisor, self.s1)

    def test_se_puede_elegir_otro_senior_revisor(self):
        self.client.force_login(self.s1)
        self.client.post(reverse("entregable_nuevo"), self.datos(senior_revisor=self.s2.pk))
        e = Entregable.objects.get(titulo="Nuevo")
        self.assertEqual((e.senior_revisor, e.contrato.senior_responsable), (self.s2, self.s1))
        # el revisor elegido lo ve y lo puede aprobar; el responsable del contrato también
        self.client.force_login(self.s2)
        self.assertEqual(self.client.get(reverse("entregable_detalle", args=[e.pk])).status_code, 200)

    def test_el_revisor_debe_ser_un_senior(self):
        self.client.force_login(self.s1)
        r = self.client.post(reverse("entregable_nuevo"), self.datos(senior_revisor=self.j2.pk))
        self.assertContains(r, "Elija un senior de la lista.")
        self.assertFalse(Entregable.objects.filter(titulo="Nuevo").exists())

    def test_errores_juntos_y_con_su_motivo(self):
        self.client.force_login(self.s1)
        r = self.client.post(reverse("entregable_nuevo"), self.datos(
            plazo="2020-01-01", c_periodo="", junior_asignado=self.j2.pk, titulo=""))
        for texto in ("El plazo no puede ser anterior a hoy.", "Falta completar el campo «Periodo».",
                      "Ese junior no está asignado al contrato elegido.", "Falta el título."):
            self.assertContains(r, texto)
        self.assertContains(r, "No se pudo guardar. Revise lo siguiente:")

    def test_el_junior_no_llega_a_la_pantalla(self):
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(reverse("entregable_nuevo")).status_code, 403)

    def test_sin_contratos_vigentes_lo_avisa(self):
        self.c1.activo = False
        self.c1.save()
        self.assertContains(self.pagina(self.plantilla), "No hay contratos vigentes a su cargo")
