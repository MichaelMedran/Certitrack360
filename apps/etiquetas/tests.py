"""SDD del Sprint 3, hito S3-H2: etiquetas (RF-41, HU-23). Caso clave 31 de la §13.

Criterios de Trello de HU-23:
  1. Etiquetas de colores según la línea de servicio en el tablero  -> LineaDeServicioTests, TarjetaYListaTests
  2. Asignar una o más etiquetas por proyecto al crear o editar     -> AsignarTests, CrearEntregableConEtiquetasTests
  3. Filtrado dinámico según la etiqueta seleccionada               -> FiltroTests
  4. Crear etiquetas personalizadas (seniors, gerente y admin)      -> CrearEtiquetaTests
"""
import datetime
import importlib

from django.apps import apps as registro
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.clientes.models import LineaServicio
from apps.entregables import filtros
from apps.entregables.models import Entregable
from apps.entregables.tests import Base
from apps.entregables.visibilidad import entregables_visibles

from . import servicios
from .models import Etiqueta

E = Entregable.Estado


class EtiquetasBase(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.urgente = Etiqueta.objects.create(nombre="Prioridad del cliente", color="ROJO", creada_por=cls.s1)
        cls.interna = Etiqueta.objects.create(nombre="Interna", color="AZUL", creada_por=cls.s1)

    def entrar(self, usuario):
        self.client.force_login(usuario)
        return self.client

    def ids_lista(self, usuario, **params):
        self.client.force_login(usuario)
        return {e.pk for e in self.client.get(reverse("entregables"), params).context["entregables"]}


# ------------------------------------------------------------------ criterio 1: según la línea de servicio

class LineaDeServicioTests(EtiquetasBase):
    def test_la_migracion_crea_una_etiqueta_por_linea_con_colores_distintos(self):
        lineas = LineaServicio.objects.all()
        self.assertGreaterEqual(lineas.count(), 5)
        for linea in lineas:
            with self.subTest(linea=linea.nombre):
                self.assertEqual(linea.etiqueta.nombre, linea.nombre)
        colores = list(Etiqueta.objects.filter(linea_servicio__isnull=False).values_list("color", flat=True))
        self.assertEqual(len(set(colores)), len(colores))

    def test_una_linea_nueva_recibe_su_etiqueta(self):
        linea = LineaServicio.objects.create(nombre="Consultoría ficticia")
        self.assertEqual(linea.etiqueta.nombre, "Consultoría ficticia")
        self.assertIn(linea.etiqueta.color, Etiqueta.Color.values)

    def test_la_migracion_tiene_reversa(self):
        migracion = importlib.import_module("apps.etiquetas.migrations.0002_etiquetas_de_las_lineas")
        total = Etiqueta.objects.filter(linea_servicio__isnull=False).count()
        migracion.borrar_etiquetas(registro, None)
        self.assertEqual(Etiqueta.objects.filter(linea_servicio__isnull=False).count(), 0)
        self.assertTrue(Etiqueta.objects.filter(pk=self.urgente.pk).exists())  # las personalizadas no se tocan
        migracion.crear_etiquetas(registro, None)
        self.assertEqual(Etiqueta.objects.filter(linea_servicio__isnull=False).count(), total)

    def test_hay_ocho_colores_cerrados_y_cada_uno_tiene_su_estilo(self):
        css = open("static/css/s3-prioridad.css", encoding="utf-8").read()
        self.assertEqual(len(Etiqueta.Color.values), 8)
        for color in Etiqueta.Color.values:
            self.assertIn(f".etq-{color.lower()}", css)


class TarjetaYListaTests(EtiquetasBase):
    def test_la_tarjeta_del_tablero_muestra_nombre_y_color_de_las_etiquetas_del_entregable_y_del_contrato(self):
        self.e1.etiquetas_asignadas.add(self.urgente)
        self.c1.etiquetas_asignadas.add(self.interna)
        r = self.entrar(self.s1).get(reverse("tablero"))
        self.assertContains(r, '<span class="etq etq-rojo">Prioridad del cliente</span>', html=True)
        self.assertContains(r, '<span class="etq etq-azul">Interna</span>', html=True)

    def test_la_lista_tambien_las_muestra_y_no_se_repiten(self):
        self.e1.etiquetas_asignadas.add(self.urgente, self.interna)
        self.c1.etiquetas_asignadas.add(self.interna)  # la misma etiqueta en el entregable y en el contrato
        r = self.entrar(self.s1).get(reverse("entregables"))
        self.assertContains(r, "Prioridad del cliente")
        self.assertContains(r, '<span class="etq etq-azul">Interna</span>', html=True, count=1)

    def test_una_etiqueta_de_baja_se_conserva_donde_ya_estaba(self):
        self.e1.etiquetas_asignadas.add(self.urgente)
        Etiqueta.objects.filter(pk=self.urgente.pk).update(activa=False)
        self.assertContains(self.entrar(self.s1).get(reverse("tablero")), "Prioridad del cliente")

    def test_las_etiquetas_se_cargan_en_un_numero_fijo_de_consultas_por_lote(self):
        def consultas(n):
            e = [self.nuevo(self.c1, self.j1, self.s1, f"L{n}-{i}") for i in range(n)]
            for x in e:
                x.etiquetas_asignadas.add(self.urgente)
            lote = list(Entregable.objects.filter(pk__in=[x.pk for x in e]).select_related("contrato"))
            with CaptureQueriesContext(connection) as c:
                servicios.enriquecer(lote)
            self.assertTrue(all(x.etiquetas for x in lote))
            return len(c)
        self.assertEqual(consultas(2), consultas(8))
        self.assertLessEqual(consultas(3), 2)

    def test_el_detalle_muestra_la_seccion_con_las_etiquetas(self):
        self.e1.etiquetas_asignadas.add(self.urgente)
        r = self.entrar(self.j1).get(reverse("entregable_detalle", args=[self.e1.pk]))
        self.assertContains(r, 'id="etiquetas"')
        self.assertContains(r, "Prioridad del cliente")
        self.assertNotContains(r, "Guardar etiquetas")  # el junior solo las ve


# ------------------------------------------------------------------ criterio 2: asignar

class AsignarTests(EtiquetasBase):
    def asignar(self, usuario, e, *etiquetas):
        self.client.force_login(usuario)
        return self.client.post(reverse("entregable_etiquetas", args=[e.pk]), {"etiquetas": [t.pk for t in etiquetas]})

    def test_el_senior_del_entregable_asigna_una_o_mas_etiquetas(self):
        r = self.asignar(self.s1, self.e1, self.urgente, self.interna)
        self.assertRedirects(r, reverse("entregable_detalle", args=[self.e1.pk]))
        self.assertEqual(set(self.e1.etiquetas_asignadas.all()), {self.urgente, self.interna})
        self.asignar(self.s1, self.e1, self.interna)  # editar: deja solo una
        self.assertEqual(set(self.e1.etiquetas_asignadas.all()), {self.interna})

    def test_gerente_y_admin_asignan(self):
        for usuario in (self.gerente, self.admin):
            self.assertEqual(self.asignar(usuario, self.e1, self.urgente).status_code, 302)
            self.assertEqual(set(self.e1.etiquetas_asignadas.all()), {self.urgente})
            self.asignar(usuario, self.e1)

    def test_el_junior_ve_el_entregable_pero_no_puede_asignar_403(self):
        self.assertEqual(self.asignar(self.j1, self.e1, self.urgente).status_code, 403)
        self.assertFalse(self.e1.etiquetas_asignadas.exists())

    def test_quien_no_ve_el_entregable_recibe_404(self):
        self.assertEqual(self.asignar(self.s2, self.e1, self.urgente).status_code, 404)
        self.assertEqual(self.asignar(self.j2, self.e1, self.urgente).status_code, 404)

    def test_no_se_asigna_una_etiqueta_de_baja_que_el_entregable_no_tenia(self):
        Etiqueta.objects.filter(pk=self.interna.pk).update(activa=False)
        self.asignar(self.s1, self.e1, self.interna)
        self.assertFalse(self.e1.etiquetas_asignadas.exists())

    def test_una_etiqueta_inexistente_no_da_error_500(self):
        self.client.force_login(self.s1)
        r = self.client.post(reverse("entregable_etiquetas", args=[self.e1.pk]), {"etiquetas": ["99999", "x", "²"]})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(self.e1.etiquetas_asignadas.exists())

    def test_el_detalle_ofrece_el_formulario_solo_a_quien_puede(self):
        pagina = reverse("entregable_detalle", args=[self.e1.pk])
        self.assertContains(self.entrar(self.s1).get(pagina), "Guardar etiquetas")
        self.assertContains(self.entrar(self.gerente).get(pagina), "Guardar etiquetas")
        self.assertNotContains(self.entrar(self.j1).get(pagina), "Guardar etiquetas")

    def test_gerente_y_admin_asignan_etiquetas_al_contrato_en_gestion(self):
        datos = {"cliente": self.cliente.pk, "numero_contrato": "C1", "fecha_inicio": "2026-01-01", "fecha_fin": "2027-01-01",
                 "linea_servicio": LineaServicio.objects.first().pk, "senior_responsable": self.s1.pk,
                 "juniors": [self.j1.pk], "activo": "on", "etiquetas": [self.interna.pk]}
        self.client.force_login(self.gerente)
        r = self.client.post(reverse("adm_editar", args=["contratos", self.c1.pk]), datos)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(set(self.c1.etiquetas_asignadas.all()), {self.interna})
        self.assertContains(self.client.get(reverse("tablero")), "Interna")  # y se ve en los entregables del contrato

    def test_el_junior_y_el_senior_no_gestionan_contratos(self):
        for usuario in (self.j1, self.s1):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(reverse("adm_editar", args=["contratos", self.c1.pk])).status_code, 403)


class CrearEntregableConEtiquetasTests(EtiquetasBase):
    def datos(self, **extra):
        d = {"plantilla": self.plantilla.pk, "contrato": self.c1.pk, "titulo": "Con etiquetas", "junior_asignado": self.j1.pk,
             "id_tdr": "TDR-1", "fecha_recepcion": self.hoy.isoformat(),
             "plazo": (self.hoy + datetime.timedelta(days=9)).isoformat(), "c_periodo": "Octubre 2026", "c_nivel": "3"}
        d.update(extra)
        return d

    def test_se_crea_con_una_o_mas_etiquetas(self):
        self.client.force_login(self.s1)
        r = self.client.post(reverse("entregable_nuevo"), self.datos(etiquetas=[self.urgente.pk, self.interna.pk]))
        self.assertEqual(r.status_code, 302)
        e = Entregable.objects.get(titulo="Con etiquetas")
        self.assertEqual(set(e.etiquetas_asignadas.all()), {self.urgente, self.interna})

    def test_sin_etiquetas_tambien_se_crea(self):
        self.client.force_login(self.s1)
        self.assertEqual(self.client.post(reverse("entregable_nuevo"), self.datos()).status_code, 302)
        self.assertFalse(Entregable.objects.get(titulo="Con etiquetas").etiquetas_asignadas.exists())

    def test_una_etiqueta_de_baja_o_inexistente_se_rechaza(self):
        Etiqueta.objects.filter(pk=self.interna.pk).update(activa=False)
        self.client.force_login(self.s1)
        for valor in (self.interna.pk, 99999, "abc"):
            with self.subTest(valor=valor):
                r = self.client.post(reverse("entregable_nuevo"), self.datos(etiquetas=[valor]))
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, "Elija")
        self.assertFalse(Entregable.objects.filter(titulo="Con etiquetas").exists())

    def test_el_formulario_ofrece_las_etiquetas_con_la_de_cada_linea_marcable(self):
        self.client.force_login(self.s1)
        r = self.client.get(reverse("entregable_nuevo"), {"plantilla": self.plantilla.pk})
        self.assertContains(r, "Prioridad del cliente")
        linea = LineaServicio.objects.first()
        self.assertContains(r, f'data-linea-id="{linea.pk}"')
        self.assertContains(r, "data-lineas-por-contrato")  # {contrato: línea} para marcar la de su línea al elegirlo
        self.assertContains(r, "js/crear.js")
        self.assertNotContains(r, "onchange")

    def test_el_senior_crea_una_etiqueta_desde_nuevo_entregable_y_vuelve(self):
        self.client.force_login(self.s1)
        destino = reverse("entregable_nuevo") + f"?plantilla={self.plantilla.pk}"
        r = self.client.post(reverse("etiqueta_nueva"), {"nombre": "Revisión legal", "color": "MORADO", "volver": destino})
        self.assertRedirects(r, destino)
        self.assertTrue(Etiqueta.objects.filter(nombre="Revisión legal", creada_por=self.s1).exists())

    def test_un_destino_externo_no_se_sigue(self):
        self.client.force_login(self.s1)
        r = self.client.post(reverse("etiqueta_nueva"), {"nombre": "Otra", "color": "ROSA", "volver": "https://ejemplo.com/x"})
        self.assertRedirects(r, reverse("etiquetas"))


# ------------------------------------------------------------------ criterio 3: filtro

class FiltroTests(EtiquetasBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.e3 = cls.nuevo(cls.c1, cls.j1, cls.s1, "E3")
        cls.e1.etiquetas_asignadas.add(cls.urgente)       # propia
        cls.c2.etiquetas_asignadas.add(cls.urgente)       # del contrato (afecta a E2)
        cls.e3.etiquetas_asignadas.add(cls.interna)

    def test_coincide_con_las_etiquetas_del_entregable_o_de_su_contrato(self):
        self.assertEqual(self.ids_lista(self.gerente, etiqueta=self.urgente.pk), {self.e1.pk, self.e2.pk})
        self.assertEqual(self.ids_lista(self.gerente, etiqueta=self.interna.pk), {self.e3.pk})

    def test_el_filtro_nunca_amplia_la_visibilidad(self):
        # S1 no ve E2 aunque el contrato C2 tenga la etiqueta; J1 tampoco.
        self.assertEqual(self.ids_lista(self.s1, etiqueta=self.urgente.pk), {self.e1.pk})
        self.assertEqual(self.ids_lista(self.j1, etiqueta=self.urgente.pk), {self.e1.pk})
        self.assertEqual(self.ids_lista(self.j2, etiqueta=self.urgente.pk), {self.e2.pk})
        visibles = set(entregables_visibles(self.s1).values_list("pk", flat=True))
        self.assertLessEqual(self.ids_lista(self.s1, etiqueta=self.urgente.pk), visibles)

    def test_no_repite_filas_cuando_entregable_y_contrato_tienen_la_misma_etiqueta(self):
        self.c1.etiquetas_asignadas.add(self.urgente)
        resultado = filtros.aplicar(entregables_visibles(self.gerente), {"etiqueta": self.urgente.pk, "orden": "plazo"})
        ids = list(resultado.queryset.values_list("pk", flat=True))
        self.assertEqual(len(ids), len(set(ids)))

    def test_se_combina_con_los_demas_filtros(self):
        self.assertEqual(self.ids_lista(self.gerente, etiqueta=self.urgente.pk, contrato=self.c2.pk), {self.e2.pk})

    def test_el_tablero_filtra_igual_y_muestra_el_chip(self):
        self.client.force_login(self.gerente)
        r = self.client.get(reverse("tablero"), {"etiqueta": self.interna.pk})
        titulos = {t.titulo for c in r.context["columnas"] for t in c["tarjetas"]}
        self.assertEqual(titulos, {"E3"})
        self.assertContains(r, "Etiqueta: Interna")

    def test_el_desplegable_solo_ofrece_etiquetas_de_lo_que_el_usuario_ve(self):
        self.client.force_login(self.s1)
        nombres = {t.nombre for t in self.client.get(reverse("entregables")).context["opciones"]["etiquetas"]}
        self.assertEqual(nombres, {"Prioridad del cliente", "Interna"})
        Etiqueta.objects.create(nombre="Solo de otro", color="VERDE").entregables.add(self.e2)
        nombres = {t.nombre for t in self.client.get(reverse("entregables")).context["opciones"]["etiquetas"]}
        self.assertNotIn("Solo de otro", nombres)

    def test_un_valor_invalido_se_ignora_y_uno_inexistente_no_devuelve_nada(self):
        todos = self.ids_lista(self.gerente)
        self.assertEqual(self.ids_lista(self.gerente, etiqueta="abc"), todos)
        self.assertEqual(self.ids_lista(self.gerente, etiqueta="99999999999999999999999"), todos)
        self.assertEqual(self.ids_lista(self.gerente, etiqueta=99999), set())


# ------------------------------------------------------------------ criterio 4: crear (caso clave 31)

class CrearEtiquetaTests(EtiquetasBase):
    def crear(self, usuario, nombre="Nueva etiqueta", color="TURQUESA"):
        self.client.force_login(usuario)
        return self.client.post(reverse("etiqueta_nueva"), {"nombre": nombre, "color": color})

    def test_senior_gerente_y_admin_crean_etiquetas_personalizadas(self):
        for i, usuario in enumerate((self.s1, self.gerente, self.admin)):
            with self.subTest(usuario=usuario.username):
                r = self.crear(usuario, f"Etiqueta {i}")
                self.assertRedirects(r, reverse("etiquetas"))
                etiqueta = Etiqueta.objects.get(nombre=f"Etiqueta {i}")
                self.assertEqual((etiqueta.creada_por, etiqueta.color, etiqueta.activa), (usuario, "TURQUESA", True))

    def test_el_junior_no_crea_403(self):
        self.assertEqual(self.crear(self.j1).status_code, 403)
        self.assertFalse(Etiqueta.objects.filter(nombre="Nueva etiqueta").exists())
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(reverse("etiqueta_nueva")).status_code, 403)
        self.assertEqual(self.client.get(reverse("etiquetas")).status_code, 403)
        self.assertEqual(self.client.get(reverse("etiqueta_editar", args=[self.urgente.pk])).status_code, 403)

    def test_sin_sesion_va_al_ingreso(self):
        self.assertEqual(self.client.get(reverse("etiquetas")).status_code, 302)
        self.assertEqual(self.client.post(reverse("etiqueta_nueva"), {"nombre": "x", "color": "ROJO"}).status_code, 302)

    def test_el_nombre_es_unico_sin_distinguir_mayusculas(self):
        r = self.crear(self.s1, "  prioridad   DEL cliente ")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Ya existe una etiqueta con ese nombre.")
        self.assertEqual(Etiqueta.objects.filter(nombre__iexact="prioridad del cliente").count(), 1)

    def test_el_color_debe_ser_de_la_lista_y_el_nombre_obligatorio(self):
        self.assertContains(self.crear(self.s1, "Con color raro", "FUCSIA"), "Elija uno de los colores de la lista.")
        self.assertContains(self.crear(self.s1, "   ", "ROJO"), "Falta el nombre")
        self.assertFalse(Etiqueta.objects.filter(nombre="Con color raro").exists())

    def test_el_senior_edita_pero_solo_gerente_y_admin_dan_de_baja(self):
        self.client.force_login(self.s1)
        url = reverse("etiqueta_editar", args=[self.interna.pk])
        self.assertEqual(self.client.post(url, {"nombre": "Interna 2", "color": "VERDE"}).status_code, 302)
        self.interna.refresh_from_db()
        self.assertEqual((self.interna.nombre, self.interna.color), ("Interna 2", "VERDE"))
        self.assertEqual(self.client.post(url, {"accion": "baja"}).status_code, 403)
        self.interna.refresh_from_db()
        self.assertTrue(self.interna.activa)
        for usuario in (self.gerente, self.admin):
            self.client.force_login(usuario)
            self.client.post(url, {"accion": "baja"})
            self.interna.refresh_from_db()
            self.assertFalse(self.interna.activa)
            self.client.post(url, {"accion": "alta"})
            self.interna.refresh_from_db()
            self.assertTrue(self.interna.activa)

    def test_la_pantalla_del_senior_no_muestra_la_barra_de_gestion_y_la_del_gerente_si(self):
        self.client.force_login(self.s1)
        r = self.client.get(reverse("etiquetas"))
        self.assertContains(r, "Prioridad del cliente")
        self.assertNotContains(r, 'aria-label="Gestión"')
        self.assertNotContains(r, "Dar de baja")
        self.client.force_login(self.gerente)
        r = self.client.get(reverse("etiquetas"))
        self.assertContains(r, 'aria-label="Gestión"')
        self.assertContains(r, "Dar de baja")

    def test_desde_el_detalle_el_senior_crea_y_asigna_en_un_paso(self):
        self.client.force_login(self.s1)
        destino = reverse("entregable_detalle", args=[self.e1.pk])
        r = self.client.post(reverse("etiqueta_nueva"), {"nombre": "Del detalle", "color": "ROSA", "volver": destino,
                                                         "entregable": self.e1.pk})
        self.assertRedirects(r, destino)
        self.assertEqual({t.nombre for t in self.e1.etiquetas_asignadas.all()}, {"Del detalle"})

    def test_no_asigna_a_un_entregable_que_no_ve(self):
        self.client.force_login(self.s1)
        self.client.post(reverse("etiqueta_nueva"), {"nombre": "Ajena", "color": "ROSA", "entregable": self.e2.pk})
        self.assertFalse(self.e2.etiquetas_asignadas.exists())

    def test_permisos_del_servicio(self):
        self.assertFalse(servicios.puede_crear(self.j1))
        self.assertTrue(all(servicios.puede_crear(u) for u in (self.s1, self.gerente, self.admin)))
        self.assertTrue(servicios.puede_asignar(self.s1, self.e1))
        self.assertFalse(servicios.puede_asignar(self.s2, self.e1))
        self.assertFalse(servicios.puede_asignar(self.j1, self.e1))
