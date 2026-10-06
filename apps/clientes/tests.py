"""Pruebas de la pantalla Gestión: pestañas, altas y ediciones, y el editor de campos de las plantillas (SDD RF-03 a RF-05)."""
import re

from django.urls import reverse

from apps.clientes.forms import CLAVE_VALIDA, FILA_VACIA
from apps.clientes.models import Cliente, Contrato, PlantillaTDR
from apps.entregables.tests import Base


def pestanas(html):
    """(texto, ¿activa?) de cada pestaña de Gestión."""
    barra = re.search(r'<nav class="pestanas".*?</nav>', html, flags=re.S).group(0)
    return [(texto, "aria-current" in atributos) for atributos, texto in re.findall(r"<a ([^>]*)>([^<]*)</a>", barra)]


class GestionTests(Base):
    def setUp(self):
        self.client.force_login(self.gerente)

    def test_el_acceso_comun_lleva_a_la_primera_pestana(self):
        self.assertRedirects(self.client.get(reverse("gestion")), reverse("adm_lista", args=["clientes"]))

    def test_las_tres_pestanas_marcan_la_activa(self):
        for entidad, activa in (("clientes", "Clientes"), ("contratos", "Contratos"), ("plantillas", "Plantillas")):
            with self.subTest(entidad=entidad):
                html = self.client.get(reverse("adm_lista", args=[entidad])).content.decode()
                self.assertEqual(pestanas(html), [(t, t == activa) for t in ("Clientes", "Contratos", "Plantillas")])

    def test_las_pestanas_tambien_estan_en_los_formularios(self):
        html = self.client.get(reverse("adm_nuevo", args=["contratos"])).content.decode()
        self.assertEqual([t for t, activa in pestanas(html) if activa], ["Contratos"])

    def test_cada_lista_ofrece_su_alta(self):
        for entidad, boton in (("clientes", "Nuevo cliente"), ("contratos", "Nuevo contrato"), ("plantillas", "Nueva plantilla")):
            with self.subTest(entidad=entidad):
                r = self.client.get(reverse("adm_lista", args=[entidad]))
                self.assertContains(r, f'<a class="boton" href="{reverse("adm_nuevo", args=[entidad])}">{boton}</a>')

    def test_el_titulo_del_formulario_concuerda_en_genero(self):
        casos = {"clientes": ("Nuevo cliente", "Editar cliente", self.cliente), "contratos": ("Nuevo contrato", "Editar contrato", self.c1),
                 "plantillas": ("Nueva plantilla", "Editar plantilla", self.plantilla)}
        for entidad, (alta, edicion, objeto) in casos.items():
            with self.subTest(entidad=entidad):
                self.assertContains(self.client.get(reverse("adm_nuevo", args=[entidad])), f"<h2>{alta}</h2>")
                self.assertContains(self.client.get(reverse("adm_editar", args=[entidad, objeto.pk])), f"<h2>{edicion}</h2>")

    def test_un_objeto_inexistente_es_404(self):
        for entidad in ("clientes", "contratos", "plantillas"):
            self.assertEqual(self.client.get(reverse("adm_editar", args=[entidad, 9999])).status_code, 404)
        self.assertEqual(self.client.get("/otras/").status_code, 404)

    def test_la_nota_de_baja_logica_solo_va_en_clientes_y_contratos(self):
        for entidad, nota in (("clientes", True), ("contratos", True), ("plantillas", False)):
            with self.subTest(entidad=entidad):
                self.assertEqual("baja lógica" in self.client.get(reverse("adm_lista", args=[entidad])).content.decode(), nota)

    def test_la_lista_de_contratos_muestra_vigencia_responsable_y_juniors(self):
        r = self.client.get(reverse("adm_lista", args=["contratos"]))
        self.assertContains(r, "01/01/2026 – 01/01/2027")
        self.assertContains(r, "<td>s1</td>")
        self.assertContains(r, "<td>j1</td>")

    def test_la_lista_de_plantillas_muestra_campos_adjuntos_y_si_es_generica(self):
        PlantillaTDR.objects.filter(pk=self.plantilla.pk).update(adjuntos_requeridos=["BORRADOR", "TDR"])
        con_cliente = PlantillaTDR.objects.create(nombre="De cliente", cliente=self.cliente, campos_requeridos=[
            {"nombre": "c_x", "etiqueta": "X", "tipo": "texto"}])
        html = self.client.get(reverse("adm_lista", args=["plantillas"])).content.decode()
        self.assertIn("Periodo, Nivel", html)
        self.assertIn("Borrador, TDR", html)
        self.assertIn("Genérica", html)
        self.assertIn("Ninguno", html)  # la plantilla de cliente no exige adjuntos
        self.assertIn(reverse("adm_editar", args=["plantillas", con_cliente.pk]), html)

    def test_alta_de_cliente(self):
        r = self.client.post(reverse("adm_nuevo", args=["clientes"]), {"nombre": "Nuevo Cliente SA", "sector": "PUBLICO", "activo": "on"},
                             follow=True)
        self.assertRedirects(r, reverse("adm_lista", args=["clientes"]))
        self.assertContains(r, '<div class="aviso aviso-success" role="status">Se guardó el cliente.</div>')
        self.assertEqual(Cliente.objects.get(nombre="Nuevo Cliente SA").sector, "PUBLICO")

    def test_validaciones_de_cliente(self):
        url = reverse("adm_nuevo", args=["clientes"])
        for datos in ({"nombre": "", "sector": "BANCA"}, {"nombre": "Otro", "sector": ""}, {"nombre": "Cliente Demo", "sector": "BANCA"},
                      {"nombre": "Otro", "sector": "NO_EXISTE"}):
            with self.subTest(datos=datos):
                r = self.client.post(url, datos)
                self.assertEqual(r.status_code, 200)
                self.assertTrue(r.context["form"].errors)
        self.assertEqual(Cliente.objects.count(), 1)

    def test_el_sector_trae_un_texto_guia_y_no_elige_nada_por_el_usuario(self):
        r = self.client.get(reverse("adm_nuevo", args=["clientes"]))
        self.assertContains(r, '<option value="" selected>— Elija el sector —</option>')

    def test_dar_de_baja_un_cliente_es_desmarcar_activo(self):
        self.client.post(reverse("adm_editar", args=["clientes", self.cliente.pk]), {"nombre": "Cliente Demo", "sector": "BANCA"})
        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.activo)
        self.assertContains(self.client.get(reverse("adm_lista", args=["clientes"])), "<td>No</td>")

    def datos_contrato(self, **extra):
        d = {"cliente": self.cliente.pk, "numero_contrato": "C9", "descripcion": "Nuevo", "fecha_inicio": "2026-03-01",
             "fecha_fin": "2027-03-01", "senior_responsable": self.s2.pk, "juniors": [self.j1.pk, self.j2.pk], "activo": "on"}
        d.update(extra)
        return d

    def test_alta_de_contrato_con_juniors(self):
        r = self.client.post(reverse("adm_nuevo", args=["contratos"]), self.datos_contrato())
        self.assertRedirects(r, reverse("adm_lista", args=["contratos"]))
        c = Contrato.objects.get(numero_contrato="C9")
        self.assertEqual((c.senior_responsable, set(c.juniors.all())), (self.s2, {self.j1, self.j2}))

    def test_el_contrato_no_admite_fechas_invertidas_ni_numeros_repetidos(self):
        url = reverse("adm_nuevo", args=["contratos"])
        r = self.client.post(url, self.datos_contrato(fecha_fin="2026-01-01"))
        self.assertIn("La fecha de fin no puede ser anterior a la fecha de inicio.", r.context["form"].errors["fecha_fin"])
        self.assertTrue(self.client.post(url, self.datos_contrato(numero_contrato="C1")).context["form"].errors["numero_contrato"])
        self.assertFalse(Contrato.objects.filter(numero_contrato="C9").exists())

    def test_el_responsable_debe_ser_senior_y_los_asignados_juniors(self):
        url = reverse("adm_nuevo", args=["contratos"])
        self.assertIn("senior_responsable", self.client.post(url, self.datos_contrato(senior_responsable=self.j1.pk)).context["form"].errors)
        self.assertIn("juniors", self.client.post(url, self.datos_contrato(juniors=[self.s1.pk])).context["form"].errors)

    def test_un_cliente_dado_de_baja_no_se_ofrece_para_contratos_nuevos(self):
        baja = Cliente.objects.create(nombre="De baja", sector="BANCA", activo=False)
        r = self.client.get(reverse("adm_nuevo", args=["contratos"]))
        self.assertNotIn(baja, r.context["form"].fields["cliente"].queryset)
        self.assertIn("cliente", self.client.post(reverse("adm_nuevo", args=["contratos"]), self.datos_contrato(cliente=baja.pk)).context["form"].errors)

    def test_un_contrato_existente_conserva_su_cliente_aunque_se_haya_dado_de_baja(self):
        Cliente.objects.filter(pk=self.cliente.pk).update(activo=False)
        r = self.client.get(reverse("adm_editar", args=["contratos", self.c1.pk]))
        self.assertIn(self.cliente, r.context["form"].fields["cliente"].queryset)

    def test_los_selectores_de_contrato_traen_texto_guia(self):
        html = self.client.get(reverse("adm_nuevo", args=["contratos"])).content.decode()
        self.assertIn('<option value="" selected>— Elija el cliente —</option>', html)
        self.assertIn('<option value="" selected>— Elija el senior —</option>', html)

    def test_junior_y_senior_no_pueden_guardar_nada(self):
        for usuario in (self.j1, self.s1):
            self.client.force_login(usuario)
            for entidad, datos in (("clientes", {"nombre": "X", "sector": "BANCA"}), ("contratos", self.datos_contrato()),
                                   ("plantillas", {"nombre": "X"})):
                with self.subTest(usuario=usuario.username, entidad=entidad):
                    self.assertEqual(self.client.post(reverse("adm_nuevo", args=[entidad]), datos).status_code, 403)
        self.assertEqual((Cliente.objects.count(), Contrato.objects.count(), PlantillaTDR.objects.count()), (1, 2, 1))


class EditorDePlantillasTests(Base):
    def setUp(self):
        self.client.force_login(self.gerente)
        self.url_nueva = reverse("adm_nuevo", args=["plantillas"])

    def datos(self, filas, **extra):
        d = {"nombre": "Plantilla nueva", "cliente": "", "formato": "PDF", "plazo_dias_por_defecto": 7,
             "campo_nombre": [f.get("nombre", "") for f in filas], "campo_etiqueta": [f["etiqueta"] for f in filas],
             "campo_tipo": [f.get("tipo", "texto") for f in filas], "campo_opciones": [f.get("opciones", "") for f in filas]}
        d.update(extra)
        return d

    def guardar(self, filas, **extra):
        r = self.client.post(self.url_nueva, self.datos(filas, **extra))
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        return PlantillaTDR.objects.get(nombre=extra.get("nombre", "Plantilla nueva"))

    # ---- guardar
    def test_crea_los_campos_en_el_orden_indicado_con_claves_generadas(self):
        p = self.guardar([{"etiqueta": "Nivel de riesgo", "tipo": "numero"}, {"etiqueta": "Periodo reportado"},
                          {"etiqueta": "Impacto", "tipo": "opcion", "opciones": "Alto, Medio, Bajo"}])
        self.assertEqual(p.campos_requeridos, [
            {"nombre": "c_nivel_de_riesgo", "etiqueta": "Nivel de riesgo", "tipo": "numero"},
            {"nombre": "c_periodo_reportado", "etiqueta": "Periodo reportado", "tipo": "texto"},
            {"nombre": "c_impacto", "etiqueta": "Impacto", "tipo": "opcion", "opciones": ["Alto", "Medio", "Bajo"]},
        ])

    def test_las_claves_con_tildes_y_signos_siguen_siendo_validas(self):
        p = self.guardar([{"etiqueta": "Fecha de emisión (ñ)/1", "tipo": "fecha"}])
        clave = p.campos_requeridos[0]["nombre"]
        self.assertRegex(clave, CLAVE_VALIDA)
        self.assertEqual(clave, "c_fecha_de_emisión__ñ__1")

    def test_los_cinco_tipos_de_campo(self):
        p = self.guardar([{"etiqueta": "A", "tipo": "texto"}, {"etiqueta": "B", "tipo": "texto_largo"}, {"etiqueta": "C", "tipo": "numero"},
                          {"etiqueta": "D", "tipo": "fecha"}, {"etiqueta": "E", "tipo": "opcion", "opciones": "x, y"}])
        self.assertEqual([c["tipo"] for c in p.campos_requeridos], ["texto", "texto_largo", "numero", "fecha", "opcion"])

    def test_se_guardan_tambien_cliente_formato_plazo_y_adjuntos(self):
        p = self.guardar([{"etiqueta": "Periodo"}], cliente=self.cliente.pk, formato="Hoja de cálculo", plazo_dias_por_defecto=21,
                         adjuntos_requeridos=["EVIDENCIA"])
        self.assertEqual((p.cliente, p.formato, p.plazo_dias_por_defecto, p.adjuntos_requeridos), (self.cliente, "Hoja de cálculo", 21, ["EVIDENCIA"]))

    def test_las_filas_en_blanco_se_ignoran(self):
        p = self.guardar([{"etiqueta": "Periodo"}, {"etiqueta": ""}, {"etiqueta": "   "}, {"etiqueta": "Nivel", "tipo": "numero"}])
        self.assertEqual([c["etiqueta"] for c in p.campos_requeridos], ["Periodo", "Nivel"])

    def test_las_etiquetas_se_guardan_sin_espacios_sobrantes(self):
        self.assertEqual(self.guardar([{"etiqueta": "  Periodo  "}]).campos_requeridos[0]["etiqueta"], "Periodo")

    def test_las_opciones_se_limpian_y_sin_repetidas(self):
        p = self.guardar([{"etiqueta": "Riesgo", "tipo": "opcion", "opciones": "Alto,  Medio , Alto,, Bajo "}])
        self.assertEqual(p.campos_requeridos[0]["opciones"], ["Alto", "Medio", "Bajo"])

    def test_un_campo_que_no_es_de_opcion_no_guarda_opciones(self):
        p = self.guardar([{"etiqueta": "Nota", "tipo": "texto", "opciones": "a, b"}])
        self.assertNotIn("opciones", p.campos_requeridos[0])

    # ---- editar: reordenar, renombrar, conservar claves
    def existente(self):
        p = PlantillaTDR.objects.create(nombre="Existente", campos_requeridos=[
            {"nombre": "c_periodo", "etiqueta": "Periodo", "tipo": "texto"},
            {"nombre": "c_nivel", "etiqueta": "Nivel", "tipo": "opcion", "opciones": ["Alto", "Bajo"]},
            {"nombre": "c_notas", "etiqueta": "Notas", "tipo": "texto_largo"}])
        return p, reverse("adm_editar", args=["plantillas", p.pk])

    def test_el_editor_muestra_los_campos_guardados_con_sus_claves_ocultas(self):
        p, url = self.existente()
        r = self.client.get(url)
        self.assertEqual(r.context["form"].filas, [
            {"nombre": "c_periodo", "etiqueta": "Periodo", "tipo": "texto", "opciones": "", "error": ""},
            {"nombre": "c_nivel", "etiqueta": "Nivel", "tipo": "opcion", "opciones": "Alto, Bajo", "error": ""},
            {"nombre": "c_notas", "etiqueta": "Notas", "tipo": "texto_largo", "opciones": "", "error": ""}])
        html = r.content.decode()
        self.assertEqual(re.findall(r'name="campo_nombre" value="([^"]*)"', html), ["c_periodo", "c_nivel", "c_notas", ""])  # + la fila modelo
        self.assertContains(r, 'name="campo_opciones" value="Alto, Bajo"')

    def test_reordenar_las_filas_cambia_el_orden_y_conserva_las_claves(self):
        p, url = self.existente()
        self.client.post(url, self.datos([
            {"nombre": "c_notas", "etiqueta": "Notas", "tipo": "texto_largo"},
            {"nombre": "c_nivel", "etiqueta": "Nivel", "tipo": "opcion", "opciones": "Alto, Bajo"},
            {"nombre": "c_periodo", "etiqueta": "Periodo"}], nombre="Existente"))
        p.refresh_from_db()
        self.assertEqual([c["nombre"] for c in p.campos_requeridos], ["c_notas", "c_nivel", "c_periodo"])

    def test_renombrar_un_campo_conserva_su_clave_interna(self):
        p, url = self.existente()
        self.client.post(url, self.datos([
            {"nombre": "c_periodo", "etiqueta": "Periodo reportado"},
            {"nombre": "c_nivel", "etiqueta": "Nivel de riesgo", "tipo": "opcion", "opciones": "Alto, Medio, Bajo"},
            {"nombre": "c_notas", "etiqueta": "Notas", "tipo": "texto_largo"}], nombre="Existente"))
        p.refresh_from_db()
        self.assertEqual([(c["nombre"], c["etiqueta"]) for c in p.campos_requeridos],
                         [("c_periodo", "Periodo reportado"), ("c_nivel", "Nivel de riesgo"), ("c_notas", "Notas")])

    def test_los_datos_de_entregables_ya_creados_siguen_ligados_tras_renombrar(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Con datos")
        antes = dict(e.datos)
        self.client.post(reverse("adm_editar", args=["plantillas", self.plantilla.pk]), self.datos([
            {"nombre": "c_periodo", "etiqueta": "Mes reportado"}, {"nombre": "c_nivel", "etiqueta": "Magnitud", "tipo": "numero"}],
            nombre="P"))
        self.plantilla.refresh_from_db()
        claves = {c["nombre"] for c in self.plantilla.campos_requeridos}
        e.refresh_from_db()
        self.assertEqual((claves, e.datos), ({"c_periodo", "c_nivel"}, antes))

    def test_una_fila_nueva_recibe_clave_y_las_viejas_no_cambian(self):
        p, url = self.existente()
        self.client.post(url, self.datos([{"nombre": "c_periodo", "etiqueta": "Periodo"}, {"etiqueta": "Responsable"}], nombre="Existente"))
        p.refresh_from_db()
        self.assertEqual([c["nombre"] for c in p.campos_requeridos], ["c_periodo", "c_responsable"])

    def test_quitar_una_fila_la_elimina_de_la_plantilla(self):
        p, url = self.existente()
        self.client.post(url, self.datos([{"nombre": "c_periodo", "etiqueta": "Periodo"}], nombre="Existente"))
        p.refresh_from_db()
        self.assertEqual([c["nombre"] for c in p.campos_requeridos], ["c_periodo"])

    def test_una_clave_manipulada_se_reemplaza_por_una_generada(self):
        for mala in ("../mal", "<script>", "sin_prefijo", "c_" + "a" * 81, "c_"):
            with self.subTest(clave=mala):
                PlantillaTDR.objects.filter(nombre="Plantilla nueva").delete()
                p = self.guardar([{"nombre": mala, "etiqueta": "Dato"}])
                self.assertEqual(p.campos_requeridos[0]["nombre"], "c_dato")

    # ---- errores
    def rechaza(self, filas, **extra):
        r = self.client.post(self.url_nueva, self.datos(filas, **extra))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(PlantillaTDR.objects.filter(nombre="Plantilla nueva").exists())
        return r

    def mensajes(self, r):
        return r.context["form"].non_field_errors()

    def test_un_campo_de_opcion_necesita_al_menos_dos_opciones(self):
        for opciones in ("", "Solo una", " , ,"):
            with self.subTest(opciones=opciones):
                r = self.rechaza([{"etiqueta": "Riesgo", "tipo": "opcion", "opciones": opciones}])
                self.assertIn("El campo «Riesgo» es de tipo opción y necesita al menos dos opciones separadas por comas.", self.mensajes(r))

    def test_las_etiquetas_repetidas_se_rechazan_y_marcan_la_segunda_fila(self):
        r = self.rechaza([{"etiqueta": "Periodo"}, {"etiqueta": "periodo"}])
        self.assertIn("El campo «periodo» está repetido.", self.mensajes(r))
        self.assertEqual([f["error"] for f in r.context["form"].filas], ["", "El campo «periodo» está repetido."])

    def test_dos_filas_con_la_misma_clave_oculta_tambien_son_repetidas(self):
        r = self.rechaza([{"nombre": "c_x", "etiqueta": "Uno"}, {"nombre": "c_x", "etiqueta": "Dos"}])
        self.assertIn("El campo «Dos» está repetido.", self.mensajes(r))

    def test_sin_campos_se_rechaza(self):
        for filas in ([{"etiqueta": ""}], [{"etiqueta": "  "}, {"etiqueta": ""}], []):
            with self.subTest(filas=len(filas)):
                self.assertIn("Agregue al menos un campo obligatorio.", self.mensajes(self.rechaza(filas)))

    def test_un_tipo_inventado_se_rechaza(self):
        r = self.rechaza([{"etiqueta": "Dato", "tipo": "html"}])
        self.assertIn("El tipo del campo «Dato» no es válido.", self.mensajes(r))

    def test_los_errores_de_varias_filas_se_informan_juntos(self):
        r = self.rechaza([{"etiqueta": "A", "tipo": "opcion", "opciones": "uno"}, {"etiqueta": "B", "tipo": "html"}])
        self.assertEqual(len(self.mensajes(r)), 2)
        self.assertEqual([bool(f["error"]) for f in r.context["form"].filas], [True, True])

    def test_al_fallar_la_pagina_conserva_lo_escrito_y_marca_la_fila_con_error(self):
        r = self.rechaza([{"etiqueta": "Periodo", "tipo": "numero"},
                          {"nombre": "c_riesgo", "etiqueta": "Riesgo", "tipo": "opcion", "opciones": "Solo una"},
                          {"etiqueta": "Notas", "tipo": "texto_largo"}], nombre="Plantilla nueva", formato="Excel", plazo_dias_por_defecto=33)
        html = r.content.decode()
        self.assertEqual(re.findall(r'name="campo_etiqueta" value="([^"]*)"', html)[:3], ["Periodo", "Riesgo", "Notas"])
        self.assertIn('name="campo_nombre" value="c_riesgo"', html)
        self.assertIn('name="campo_opciones" value="Solo una"', html)
        self.assertEqual(html.count('<tr class="con-error">'), 1)
        self.assertIn('<div class="errorlist" role="alert">El campo «Riesgo» es de tipo opción', html)
        self.assertIn('value="Excel"', html)
        self.assertIn('value="33"', html)
        self.assertEqual(re.findall(r'<option value="(\w+)" selected>', html.split('<tbody id="filas-campos">')[1].split("</tbody>")[0]),
                         ["numero", "opcion", "texto_largo"])

    def test_al_fallar_se_conservan_los_adjuntos_marcados(self):
        r = self.rechaza([{"etiqueta": ""}], adjuntos_requeridos=["TDR", "EVIDENCIA"])
        self.assertEqual(sorted(r.context["form"]["adjuntos_requeridos"].value()), ["EVIDENCIA", "TDR"])
        self.assertRegex(r.content.decode(), r'value="TDR"[^>]*checked')

    def test_un_nombre_vacio_tambien_se_informa_sin_perder_las_filas(self):
        r = self.rechaza([{"etiqueta": "Periodo"}], nombre="")
        self.assertTrue(r.context["form"].errors["nombre"])
        self.assertEqual([f["etiqueta"] for f in r.context["form"].filas], ["Periodo"])

    # ---- pantalla
    def test_la_plantilla_nueva_trae_una_fila_vacia_y_la_fila_modelo_para_agregar(self):
        r = self.client.get(self.url_nueva)
        self.assertEqual(r.context["form"].filas, [FILA_VACIA])
        html = r.content.decode()
        self.assertEqual(html.count('<template id="fila-vacia">'), 1)
        self.assertIn('id="agregar-campo"', html)
        self.assertEqual(html.count('name="campo_etiqueta"'), 2)  # la fila visible y la fila modelo
        self.assertIn("js/plantilla.js", html)

    def test_el_script_del_editor_solo_se_carga_en_las_plantillas(self):
        for entidad, carga in (("plantillas", True), ("clientes", False), ("contratos", False)):
            with self.subTest(entidad=entidad):
                self.assertEqual("js/plantilla.js" in self.client.get(reverse("adm_nuevo", args=[entidad])).content.decode(), carga)

    def test_cada_control_de_una_fila_tiene_nombre_accesible(self):
        html = self.client.get(self.url_nueva).content.decode()
        for etiqueta in ("Etiqueta del campo", "Tipo del campo", "Opciones separadas por comas", "Subir el campo", "Bajar el campo"):
            self.assertIn(f'aria-label="{etiqueta}"', html)

    def test_las_opciones_solo_se_ven_en_los_campos_de_opcion(self):
        p, url = self.existente()
        filas = re.findall(r"<tr.*?</tr>", self.client.get(url).content.decode().split('<tbody id="filas-campos">')[1], flags=re.S)
        ocultas = [bool(re.search(r'name="campo_opciones"[^>]*class="oculto"', f)) for f in filas[:3]]
        self.assertEqual(ocultas, [True, False, True])  # periodo (texto), nivel (opción), notas (texto largo)

    def test_los_campos_guardados_se_piden_al_crear_un_entregable(self):
        p = self.guardar([{"etiqueta": "Nivel de riesgo", "tipo": "numero"}, {"etiqueta": "Impacto", "tipo": "opcion", "opciones": "Alto, Bajo"}])
        self.client.force_login(self.s1)
        form = self.client.get(reverse("entregable_nuevo"), {"plantilla": p.pk}).context["form"]
        self.assertEqual([(c.name, c.label) for c in form.campos_plantilla], [("c_nivel_de_riesgo", "Nivel de riesgo"), ("c_impacto", "Impacto")])
