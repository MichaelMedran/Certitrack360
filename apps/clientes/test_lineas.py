"""SDD del Sprint 2, hito S2-H1 · RF-24: catálogo de líneas de servicio (pestaña de Gestión /lineas-servicio/), línea del
contrato (obligatoria en el formulario) y filtro por línea en el tablero y la lista (wireframes s2-personal y s2-tablero)."""
import importlib
import re

from django.apps import apps as registro
from django.db.models import ProtectedError
from django.test import Client
from django.urls import reverse

from apps.clientes.models import LINEAS_INICIALES, Contrato, LineaServicio
from apps.clientes.tests import pestanas
from apps.entregables import filtros
from apps.entregables.test_filtros import FiltrosBase
from apps.entregables.tests import Base
from apps.entregables.visibilidad import entregables_visibles

URL = "/lineas-servicio/"


def linea(nombre):
    return LineaServicio.objects.get(nombre=nombre)


class CatalogoTests(Base):
    migracion = importlib.import_module("apps.clientes.migrations.0005_lineas_de_servicio")

    def test_la_migracion_crea_las_cinco_lineas_del_tablero_activas(self):
        self.assertEqual(set(LineaServicio.objects.values_list("nombre", flat=True)), set(LINEAS_INICIALES))
        self.assertFalse(LineaServicio.objects.filter(activa=False).exists())
        self.assertEqual(set(self.migracion.LINEAS), set(LINEAS_INICIALES))

    def test_la_migracion_de_datos_tiene_reversa_y_se_puede_repetir(self):
        self.migracion.borrar_lineas(registro, None)
        self.assertFalse(LineaServicio.objects.filter(nombre__in=LINEAS_INICIALES).exists())
        self.migracion.crear_lineas(registro, None)
        self.migracion.crear_lineas(registro, None)  # no duplica
        self.assertEqual(LineaServicio.objects.filter(nombre__in=LINEAS_INICIALES).count(), 5)

    def test_una_linea_en_uso_no_se_puede_borrar(self):
        self.c1.linea_servicio = linea("BPO")
        self.c1.save()
        with self.assertRaises(ProtectedError):
            linea("BPO").delete()

    def test_los_contratos_anteriores_quedan_sin_linea(self):
        self.assertIsNone(Contrato.objects.get(pk=self.c1.pk).linea_servicio)


class PantallaDeLineasTests(Base):
    def ver(self, usuario, params=None):
        self.client.force_login(usuario)
        return self.client.get(URL, params or {})

    def guardar(self, datos, usuario=None):
        self.client.force_login(usuario or self.gerente)
        return self.client.post(URL, datos)

    def test_la_ruta_es_la_del_sdd(self):
        self.assertEqual(reverse("lineas_servicio"), URL)

    def test_sin_sesion_va_al_ingreso(self):
        for metodo in ("get", "post"):
            r = getattr(self.client, metodo)(URL)
            self.assertEqual(r.status_code, 302)
            self.assertTrue(r["Location"].startswith(reverse("login")))

    def test_junior_y_senior_reciben_403_como_en_el_resto_de_gestion(self):
        for usuario in (self.j1, self.j2, self.s1, self.s2):
            with self.subTest(usuario=usuario.username):
                self.assertEqual(self.ver(usuario).status_code, 403)
                self.assertEqual(self.guardar({"nombre": "Intrusa", "activa": "on"}, usuario).status_code, 403)
                self.assertEqual(self.guardar({"linea": linea("BPO").pk, "nombre": "Renombrada"}, usuario).status_code, 403)
        self.assertFalse(LineaServicio.objects.filter(nombre__in=["Intrusa", "Renombrada"]).exists())
        self.assertTrue(linea("BPO").activa)

    def test_gerente_y_admin_la_ven(self):
        for usuario in (self.gerente, self.admin):
            self.assertEqual(self.ver(usuario).status_code, 200)

    def test_lista_las_lineas_con_sus_contratos_y_el_estado_en_texto(self):
        Contrato.objects.filter(pk__in=[self.c1.pk, self.c2.pk]).update(linea_servicio=linea("BPO"))
        LineaServicio.objects.filter(nombre="Estado").update(activa=False)
        html = self.ver(self.gerente).content.decode()
        filas = {nombre: (n, estado) for nombre, n, estado in re.findall(
            r'<tr><td>([^<]+)</td><td class="num">(\d+)</td><td>(Activa|Inactiva)</td>', html)}
        self.assertEqual(filas["BPO"], ("2", "Activa"))
        self.assertEqual(filas["Custodia"], ("0", "Activa"))
        self.assertEqual(filas["Estado"], ("0", "Inactiva"))
        self.assertEqual(len(filas), 5)

    def test_es_una_pestana_de_gestion_y_la_barra_marca_gestion(self):
        html = self.ver(self.gerente).content.decode()
        self.assertEqual(pestanas(html), [("Clientes", False), ("Contratos", False), ("Plantillas", False),
                                          ("Fichas", False), ("Personal", False), ("Líneas de servicio", True)])
        self.assertEqual(re.findall(r'<nav aria-label="Principal">.*?aria-current="page">([^<]+)</a>', html, flags=re.S),
                         ["Gestión"])
        self.assertEqual(html.count("<h1"), 1)
        self.assertNotIn("Eliminar", html)  # la baja es lógica: no hay borrado

    def test_crear_una_linea(self):
        self.client.force_login(self.gerente)
        r = self.client.post(URL, {"nombre": "  Seguros   generales ", "activa": "on"}, follow=True)
        self.assertRedirects(r, URL)
        self.assertContains(r, "Se creó la línea de servicio «Seguros generales».")
        self.assertTrue(linea("Seguros generales").activa)

    def test_el_catalogo_se_lista_en_orden_alfabetico(self):
        self.guardar({"nombre": "Archivo", "activa": "on"})
        html = self.ver(self.gerente).content.decode()
        nombres = re.findall(r'<tr><td>([^<]+)</td><td class="num">', html)
        self.assertEqual(nombres, ["Archivo", "Banca", "BPO", "Custodia", "Digitalización", "Estado"])

    def test_el_nombre_es_obligatorio(self):
        r = self.guardar({"nombre": "   ", "activa": "on"})
        self.assertContains(r, "Falta el nombre de la línea de servicio.")
        self.assertEqual(LineaServicio.objects.count(), 5)

    def test_un_nombre_repetido_se_rechaza_sin_distinguir_mayusculas_ni_tildes(self):
        for nombre in ("bpo", " Banca ", "DIGITALIZACIÓN"):
            with self.subTest(nombre=nombre):
                self.assertContains(self.guardar({"nombre": nombre, "activa": "on"}), "Ya existe una línea de servicio con ese nombre.")
        self.assertEqual(LineaServicio.objects.count(), 5)

    def test_renombrar_conserva_los_contratos(self):
        bpo = linea("BPO")
        self.c1.linea_servicio = bpo
        self.c1.save()
        r = self.guardar({"linea": bpo.pk, "nombre": "BPO y back office", "activa": "on"})
        self.assertRedirects(r, URL)
        bpo.refresh_from_db()
        self.assertEqual(bpo.nombre, "BPO y back office")
        self.assertEqual(Contrato.objects.get(pk=self.c1.pk).linea_servicio, bpo)
        self.assertEqual(LineaServicio.objects.count(), 5)  # editar no crea otra

    def test_renombrar_con_su_mismo_nombre_no_es_repetido(self):
        self.assertRedirects(self.guardar({"linea": linea("Banca").pk, "nombre": "banca", "activa": "on"}), URL)
        self.assertTrue(LineaServicio.objects.filter(nombre="banca").exists())

    def test_desactivar_y_volver_a_activar(self):
        custodia = linea("Custodia")
        self.guardar({"linea": custodia.pk, "nombre": "Custodia"})  # sin «activa»: queda inactiva
        custodia.refresh_from_db()
        self.assertFalse(custodia.activa)
        self.guardar({"linea": custodia.pk, "nombre": "Custodia", "activa": "on"})
        custodia.refresh_from_db()
        self.assertTrue(custodia.activa)

    def test_formularios_de_alta_y_edicion(self):
        self.assertIsNone(self.ver(self.gerente).context["form"])
        alta = self.ver(self.gerente, {"nueva": ""})
        self.assertContains(alta, "Nueva línea de servicio")
        self.assertContains(alta, '<input type="checkbox" name="activa"')
        edicion = self.ver(self.gerente, {"editar": linea("Banca").pk})
        self.assertContains(edicion, "Editar «Banca»")
        self.assertContains(edicion, f'<input type="hidden" name="linea" value="{linea("Banca").pk}">')
        self.assertContains(edicion, 'value="Banca"')
        self.assertEqual(self.ver(self.gerente, {"editar": 99999}).status_code, 404)
        self.assertEqual(self.guardar({"linea": 99999, "nombre": "X"}).status_code, 404)

    def test_un_id_mal_escrito_o_fuera_de_rango_es_404_y_no_crea_otra_linea(self):
        # Revisión de S2-H1 (S2-H1-H2-ajustes): antes un id no numérico creaba una línea nueva y uno enorme daba error 500.
        for valor in ("abc", "", "99999999999999999999999", str(2**63)):
            with self.subTest(valor=valor):
                self.assertEqual(self.ver(self.gerente, {"editar": valor}).status_code, 404)
                self.assertEqual(self.guardar({"linea": valor, "nombre": "Fantasma", "activa": "on"}).status_code, 404)
        self.assertFalse(LineaServicio.objects.filter(nombre="Fantasma").exists())
        self.assertEqual(LineaServicio.objects.count(), 5)

    def test_exige_csrf(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.gerente)
        self.assertEqual(c.post(URL, {"nombre": "Sin token", "activa": "on"}).status_code, 403)
        self.assertFalse(LineaServicio.objects.filter(nombre="Sin token").exists())

    def test_no_se_guarda_en_la_cache(self):
        self.assertIn("no-store", self.ver(self.gerente)["Cache-Control"])


class ContratoConLineaTests(Base):
    def setUp(self):
        self.client.force_login(self.gerente)

    def datos(self, **extra):
        d = {"cliente": self.cliente.pk, "numero_contrato": "C9", "descripcion": "Nuevo", "linea_servicio": linea("BPO").pk,
             "fecha_inicio": "2026-03-01", "fecha_fin": "2027-03-01", "senior_responsable": self.s2.pk,
             "juniors": [self.j1.pk], "activo": "on"}
        d.update(extra)
        return d

    def test_la_linea_es_obligatoria_en_el_formulario(self):
        r = self.client.post(reverse("adm_nuevo", args=["contratos"]), self.datos(linea_servicio=""))
        self.assertEqual(r.status_code, 200)
        self.assertIn("Falta elegir la línea de servicio.", r.context["form"].errors["linea_servicio"])
        self.assertFalse(Contrato.objects.filter(numero_contrato="C9").exists())

    def test_alta_con_su_linea(self):
        self.assertRedirects(self.client.post(reverse("adm_nuevo", args=["contratos"]), self.datos()),
                             reverse("adm_lista", args=["contratos"]))
        self.assertEqual(Contrato.objects.get(numero_contrato="C9").linea_servicio, linea("BPO"))

    def test_el_formulario_la_pide_con_texto_guia(self):
        html = self.client.get(reverse("adm_nuevo", args=["contratos"])).content.decode()
        self.assertIn('<label for="id_linea_servicio">Línea de servicio:</label>', html)
        self.assertRegex(html, r'<select name="linea_servicio" required id="id_linea_servicio">\s*'
                               r'<option value="" selected>— Elija la línea de servicio —</option>')

    def test_una_linea_inactiva_no_se_ofrece_para_contratos_nuevos(self):
        LineaServicio.objects.filter(nombre="Estado").update(activa=False)
        r = self.client.get(reverse("adm_nuevo", args=["contratos"]))
        self.assertNotIn(linea("Estado"), r.context["form"].fields["linea_servicio"].queryset)
        r = self.client.post(reverse("adm_nuevo", args=["contratos"]), self.datos(linea_servicio=linea("Estado").pk))
        self.assertIn("Elija una línea de servicio activa de la lista.", r.context["form"].errors["linea_servicio"])

    def test_un_contrato_conserva_su_linea_aunque_se_desactive(self):
        self.c1.linea_servicio = linea("Custodia")
        self.c1.save()
        LineaServicio.objects.filter(nombre="Custodia").update(activa=False)
        url = reverse("adm_editar", args=["contratos", self.c1.pk])
        self.assertIn(linea("Custodia"), self.client.get(url).context["form"].fields["linea_servicio"].queryset)
        datos = self.datos(numero_contrato="C1", linea_servicio=linea("Custodia").pk, senior_responsable=self.s1.pk)
        self.assertEqual(self.client.post(url, datos).status_code, 302)
        self.assertEqual(Contrato.objects.get(pk=self.c1.pk).linea_servicio, linea("Custodia"))

    def test_una_peticion_sin_la_clave_se_rechaza_en_el_alta_y_en_la_edicion(self):
        # Obligatoria SIEMPRE en el formulario, aunque la petición no traiga el campo.
        datos = self.datos()
        del datos["linea_servicio"]
        r = self.client.post(reverse("adm_nuevo", args=["contratos"]), datos)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Falta elegir la línea de servicio.", r.context["form"].errors["linea_servicio"])
        self.assertFalse(Contrato.objects.filter(numero_contrato="C9").exists())
        self.c1.linea_servicio = linea("Banca")
        self.c1.save()
        datos = self.datos(numero_contrato="C1", senior_responsable=self.s1.pk, descripcion="Cambiada")
        del datos["linea_servicio"]
        r = self.client.post(reverse("adm_editar", args=["contratos", self.c1.pk]), datos)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Falta elegir la línea de servicio.", r.context["form"].errors["linea_servicio"])
        c1 = Contrato.objects.get(pk=self.c1.pk)
        self.assertEqual((c1.linea_servicio, c1.descripcion), (linea("Banca"), self.c1.descripcion))

    def test_en_la_base_de_datos_un_contrato_puede_seguir_sin_linea(self):
        Contrato.objects.filter(pk=self.c1.pk).update(linea_servicio=None)
        self.assertIsNone(Contrato.objects.get(pk=self.c1.pk).linea_servicio)

    def test_la_lista_de_contratos_muestra_la_linea(self):
        self.c1.linea_servicio = linea("Digitalización")
        self.c1.save()
        html = self.client.get(reverse("adm_lista", args=["contratos"])).content.decode()
        self.assertIn("<th>Línea de servicio</th>", html)
        self.assertIn("<td>Digitalización</td>", html)
        self.assertIn("<td>Sin asignar</td>", html)  # C2 todavía no la tiene


class FiltroPorLineaTests(FiltrosBase):
    """Tablero y lista suman el filtro por línea de servicio (s2-tablero, anotación 1); nunca amplía lo visible."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Contrato.objects.filter(pk=cls.c1.pk).update(linea_servicio=linea("BPO"))
        Contrato.objects.filter(pk=cls.c2.pk).update(linea_servicio=linea("Banca"))  # c3 sin línea

    def test_filtra_por_la_linea_del_contrato(self):
        self.assertEqual(self.ver_set(self.gerente, linea=linea("BPO").pk), {"E1", "a-vencido", "b-hoy", "g-hecho"})
        self.assertEqual(self.ver_set(self.gerente, linea=linea("Banca").pk), {"E2", "f-proximo", "h-vencido"})
        self.assertEqual(self.ver_set(self.gerente, linea=linea("Estado").pk), set())

    def test_nunca_amplia_lo_visible(self):
        self.assertEqual(self.ver(self.j1, linea=linea("Banca").pk), [])  # j1 no tiene nada en C2
        self.assertEqual(self.ver(self.s2, linea=linea("BPO").pk), [])
        for usuario in (self.j1, self.j2, self.s1, self.s2, self.gerente, self.admin):
            visibles = set(entregables_visibles(usuario).values_list("pk", flat=True))
            for valor in [linea(n).pk for n in LINEAS_INICIALES] + [99999]:
                obtenidos = set(filtros.aplicar(entregables_visibles(usuario), {"linea": valor}).queryset.values_list("pk", flat=True))
                self.assertLessEqual(obtenidos, visibles, f"{usuario.username} {valor}")

    def test_las_opciones_solo_traen_lineas_de_lo_visible(self):
        self.assertEqual({l.nombre for l in filtros.opciones(self.j1)["lineas"]}, {"BPO"})
        self.assertEqual({l.nombre for l in filtros.opciones(self.j2)["lineas"]}, {"Banca"})
        self.assertEqual({l.nombre for l in filtros.opciones(self.gerente)["lineas"]}, {"BPO", "Banca"})

    def test_el_panel_y_los_chips_de_tablero_y_lista(self):
        self.client.force_login(self.gerente)
        for nombre in ("tablero", "entregables"):
            with self.subTest(pantalla=nombre):
                r = self.client.get(reverse(nombre), {"linea": linea("BPO").pk})
                self.assertEqual(r.context["filtros_activos"], {"linea": linea("BPO").pk})
                self.assertRegex(r.content.decode(), r'<label for="f-linea">Línea de servicio</label>\s*<select id="f-linea" name="linea">')
                self.assertContains(r, f'<option value="{linea("BPO").pk}" selected>BPO</option>')
                self.assertEqual([c["texto"] for c in r.context["chips"]], ["Línea de servicio: BPO"])

    def test_un_valor_no_valido_se_ignora(self):
        res = filtros.aplicar(entregables_visibles(self.gerente), {"linea": "abc"})
        self.assertEqual(res.activos, {})

    def test_ids_fuera_de_rango_se_ignoran_sin_error_500(self):
        # Revisión de S2-H1 (S2-H1-H2-ajustes): un id mayor que un entero de 64 bits hacía fallar la consulta.
        self.client.force_login(self.gerente)
        for valor in ("99999999999999999999999", str(2**63), str(-(2**63) - 1), "9" * 5000):
            for clave in ("linea", "cliente", "contrato", "responsable"):
                self.assertNotIn(clave, filtros.aplicar(entregables_visibles(self.gerente), {clave: valor}).activos)
                for nombre in ("tablero", "entregables"):
                    with self.subTest(clave=clave, valor=valor[:30], pantalla=nombre):
                        self.assertEqual(self.client.get(reverse(nombre), {clave: valor}).status_code, 200)
        self.assertEqual(filtros.entero(str(2**63 - 1)), 2**63 - 1)
        self.assertEqual(filtros.entero(" 7 "), 7)


class NavegacionTests(Base):
    """Cada hito agrega su pestaña cuando crea la pantalla: no hay enlaces a pantallas que todavía no existen."""

    def test_no_hay_enlaces_a_pantallas_futuras(self):
        for usuario in (self.j1, self.s1, self.gerente, self.admin):
            self.client.force_login(usuario)
            for nombre in ("inicio", "tablero", "calendario", "entregables"):
                html = self.client.get(reverse(nombre)).content.decode()
                # /observaciones/ (S2-H3), /entregas/ (S2-H4), /personal/ (S2-H6) y /tiempos/ (S2-H7) ya existen.
                for ruta in ("/repositorio/", "/indicadores/", "/buscar/",
                             "/incorporacion/", "/procedimientos/"):
                    self.assertNotIn(f'href="{ruta}', html, f"{usuario.username} {nombre} {ruta}")

    def test_todas_las_pestanas_de_gestion_abren(self):
        self.client.force_login(self.gerente)
        html = self.client.get(reverse("adm_lista", args=["clientes"])).content.decode()
        barra = re.search(r'<nav class="pestanas".*?</nav>', html, flags=re.S).group(0)
        for href in re.findall(r'href="([^"]+)"', barra):
            with self.subTest(href=href):
                self.assertEqual(self.client.get(href).status_code, 200)
