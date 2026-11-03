"""SDD del Sprint 2, hito S2-H1 · RF-20 (caso 13): código único CT-AAAA-NNNNN, ID-TDR, línea de servicio y fecha de
recepción del entregable (HU-01), en el formulario, en el detalle, en el tablero, en la lista, en los avisos y en los datos
que ya existían (migración de relleno)."""
import datetime
import importlib
import io
import re
from unittest import mock

from django.apps import apps as registro
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.alertas.models import Notificacion
from apps.clientes.models import Contrato, LineaServicio
from apps.conocimiento import ollama
from apps.entregables import servicios
from apps.entregables.models import Entregable, generar_codigo
from apps.entregables.testing import MediaTemporal
from apps.entregables.tests import Base

E = Entregable.Estado
FORMATO = re.compile(r"CT-(\d{4})-(\d{5,})")
UTC = datetime.timezone.utc


def sin_ollama(ruta, cuerpo, timeout):
    raise ollama.OllamaNoDisponible("simulado")


class CodigoTests(Base):
    def test_todo_entregable_nuevo_tiene_su_codigo_con_el_formato_del_sdd(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Nuevo")
        anio = timezone.localdate().year
        self.assertEqual(e.codigo, f"CT-{anio}-{e.pk:05d}")
        e.refresh_from_db()
        self.assertEqual(e.codigo, f"CT-{anio}-{e.pk:05d}")
        self.assertRegex(e.codigo, FORMATO)

    def test_los_codigos_no_se_repiten_y_la_base_de_datos_lo_garantiza(self):
        nuevos = [self.nuevo(self.c1, self.j1, self.s1, f"N{i}") for i in range(5)]
        codigos = list(Entregable.objects.values_list("codigo", flat=True))
        self.assertEqual(len(codigos), len(set(codigos)))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Entregable.objects.filter(pk=nuevos[0].pk).update(codigo=nuevos[1].codigo)

    def test_ningun_entregable_queda_sin_codigo(self):
        self.nuevo(self.c1, self.j1, self.s1, "Otro")
        self.assertFalse(Entregable.objects.filter(codigo__isnull=True).exists())

    def test_el_codigo_no_cambia_al_editar_ni_si_cambia_el_prefijo(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Estable")
        antes = e.codigo
        with override_settings(CODIGO_PREFIJO="QA"):
            e.titulo = "Estable (corregido)"
            e.save()
        e.refresh_from_db()
        self.assertEqual(e.codigo, antes)

    @override_settings(CODIGO_PREFIJO="QA")
    def test_el_prefijo_es_configurable(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Con prefijo")
        self.assertEqual(e.codigo, f"QA-{timezone.localdate().year}-{e.pk:05d}")

    def test_el_anio_y_la_recepcion_son_los_de_lima(self):
        # 2027-01-01 03:00 UTC es todavía 31/12/2026 en Lima (UTC-5).
        with mock.patch("django.utils.timezone.now", return_value=datetime.datetime(2027, 1, 1, 3, 0, tzinfo=UTC)):
            e = self.nuevo(self.c1, self.j1, self.s1, "Fin de año")
        self.assertEqual(e.codigo, f"CT-2026-{e.pk:05d}")
        self.assertEqual(e.fecha_recepcion, datetime.date(2026, 12, 31))
        self.assertEqual(generar_codigo(7, datetime.datetime(2026, 6, 1, 12, 0, tzinfo=UTC)), "CT-2026-00007")

    def test_el_codigo_se_asigna_en_la_misma_transaccion_que_el_alta(self):
        antes = Entregable.objects.count()
        with mock.patch("apps.entregables.models.generar_codigo", side_effect=RuntimeError("falla simulada")):
            with self.assertRaises(RuntimeError):
                self.nuevo(self.c1, self.j1, self.s1, "No debe quedar")
        self.assertEqual(Entregable.objects.count(), antes)  # sin código no queda nada a medias
        self.assertFalse(Entregable.objects.filter(titulo="No debe quedar").exists())

    def test_la_fecha_de_recepcion_por_defecto_es_la_de_creacion_y_se_respeta_la_indicada(self):
        self.assertEqual(self.nuevo(self.c1, self.j1, self.s1, "Sin fecha").fecha_recepcion, timezone.localdate())
        e = Entregable.objects.create(
            contrato=self.c1, plantilla=self.plantilla, titulo="Con fecha", plazo=self.hoy, junior_asignado=self.j1,
            senior_revisor=self.s1, creado_por=self.s1, fecha_recepcion=self.hoy - datetime.timedelta(days=3))
        self.assertEqual(e.fecha_recepcion, self.hoy - datetime.timedelta(days=3))

    def test_el_panel_tecnico_tambien_asigna_el_codigo_y_lo_muestra_sin_dejar_editarlo(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("admin:entregables_entregable_add"), {
            "contrato": self.c1.pk, "plantilla": self.plantilla.pk, "titulo": "Desde el panel", "id_tdr": "",
            "fecha_recepcion": "", "datos": "{}", "plazo": (self.hoy + datetime.timedelta(days=3)).isoformat(),
            "estado": "A_REALIZAR", "junior_asignado": self.j1.pk, "senior_revisor": self.s1.pk, "creado_por": self.admin.pk,
        })
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["adminform"].form.errors)
        e = Entregable.objects.get(titulo="Desde el panel")
        self.assertEqual(e.codigo, f"CT-{timezone.localdate().year}-{e.pk:05d}")
        pagina = self.client.get(reverse("admin:entregables_entregable_change", args=[e.pk])).content.decode()
        self.assertIn(e.codigo, pagina)
        self.assertNotIn('name="codigo"', pagina)

    def test_el_codigo_esta_en_el_detalle_la_tarjeta_y_la_lista(self):
        self.client.force_login(self.j1)
        detalle = self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).content.decode()
        self.assertIn(f'<h1>E1 <span class="etiqueta codigo">{self.e1.codigo}</span></h1>', detalle)
        self.assertIn(f"<title>{self.e1.codigo} · E1 · CertiTrack 360</title>", detalle)
        tablero = self.client.get(reverse("tablero")).content.decode()
        self.assertIn(f'<div class="codigo">{self.e1.codigo}</div>', tablero)
        lista = self.client.get(reverse("entregables")).content.decode()
        self.assertIn(f'<td class="codigo">{self.e1.codigo}</td>', lista)

    def test_quien_no_ve_el_entregable_tampoco_ve_su_codigo(self):
        for ajeno in (self.j2, self.s2):  # mismo rol, otro contrato
            with self.subTest(usuario=ajeno.username):
                self.client.force_login(ajeno)
                self.assertEqual(self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).status_code, 404)
                for nombre in ("tablero", "entregables"):
                    self.assertNotContains(self.client.get(reverse(nombre)), self.e1.codigo)
                self.assertNotIn(self.e1.pk, {ev["id"] for ev in self.client.get(reverse("calendario_eventos")).json()})

    def test_los_avisos_llevan_el_codigo(self):
        servicios.registrar_creacion(self.e1, self.s1)
        asignacion = Notificacion.objects.get(entregable=self.e1, tipo="ASIGNACION")
        self.assertEqual(asignacion.mensaje, f"Se le asignó {self.e1.codigo} «E1» (vence el {self.e1.plazo:%d/%m/%Y}).")
        servicios.mover(self.e1, E.EN_PROCESO, self.j1)
        servicios.mover(self.e1, E.VERIFICACION_SENIOR, self.j1)
        revision = Notificacion.objects.get(entregable=self.e1, tipo="VERIFICACION")
        self.assertEqual(revision.mensaje, f"{self.e1.codigo} «E1» pasó a «{E.VERIFICACION_SENIOR.label}» y espera su revisión.")
        servicios.mover(self.e1, E.EN_PROCESO, self.s1, tipo_error="FORMATO", descripcion="Ajustar títulos")
        devuelto = Notificacion.objects.get(entregable=self.e1, tipo="OBSERVACION")
        self.assertEqual(devuelto.mensaje, f"{self.e1.codigo} «E1» fue devuelto con una observación.")

    def test_un_titulo_largo_no_desborda_el_aviso(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "T" * 200)
        servicios.registrar_creacion(e, self.s1)
        mensaje = Notificacion.objects.get(entregable=e, tipo="ASIGNACION").mensaje
        self.assertLessEqual(len(mensaje), Notificacion._meta.get_field("mensaje").max_length)
        self.assertIn(e.codigo, mensaje)


class NuevoEntregableConRecepcionTests(Base):
    """El formulario «Nuevo entregable» pide ID-TDR y fecha de recepción (Poka-Yoke ampliado, wireframe s2-nuevo)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.digitalizacion = LineaServicio.objects.get(nombre="Digitalización")
        cls.c1.linea_servicio = cls.digitalizacion
        cls.c1.save()

    def datos(self, **extra):
        d = {"plantilla": self.plantilla.pk, "contrato": self.c1.pk, "titulo": "Nuevo", "junior_asignado": self.j1.pk,
             "id_tdr": "TDR-CD-014", "fecha_recepcion": (self.hoy - datetime.timedelta(days=1)).isoformat(),
             "plazo": (self.hoy + datetime.timedelta(days=5)).isoformat(), "c_periodo": "Octubre 2026", "c_nivel": "3"}
        d.update(extra)
        return d

    def post(self, follow=False, **extra):
        self.client.force_login(self.s1)
        return self.client.post(reverse("entregable_nuevo"), self.datos(**extra), follow=follow)

    def pagina(self):
        self.client.force_login(self.s1)
        return self.client.get(reverse("entregable_nuevo"), {"plantilla": self.plantilla.pk})

    def rechaza(self, texto, **extra):
        r = self.post(**extra)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, texto)
        self.assertFalse(Entregable.objects.filter(titulo="Nuevo").exists())
        return r

    def test_crea_el_entregable_con_sus_datos_de_recepcion_y_su_codigo(self):
        r = self.post(follow=True)
        e = Entregable.objects.get(titulo="Nuevo")
        self.assertEqual((e.id_tdr, e.fecha_recepcion), ("TDR-CD-014", self.hoy - datetime.timedelta(days=1)))
        self.assertRegex(e.codigo, FORMATO)
        self.assertRedirects(r, reverse("entregable_detalle", args=[e.pk]))
        self.assertContains(r, f"El entregable {e.codigo} se creó y se asignó al junior.")
        self.assertEqual(e.historial.count(), 1)
        self.assertIn(e.codigo, Notificacion.objects.get(entregable=e, tipo="ASIGNACION").mensaje)

    def test_falta_el_id_tdr(self):
        self.rechaza("Falta el ID-TDR.", id_tdr="   ")

    def test_falta_la_fecha_de_recepcion(self):
        self.rechaza("Falta la fecha de recepción.", fecha_recepcion="")

    def test_la_fecha_de_recepcion_no_puede_ser_futura(self):
        self.rechaza("La fecha de recepción no puede ser futura.", fecha_recepcion=(self.hoy + datetime.timedelta(days=1)).isoformat())

    def test_la_recepcion_no_puede_ser_posterior_al_plazo(self):
        r = self.rechaza("La fecha de recepción no puede ser posterior al plazo.",
                         fecha_recepcion=(self.hoy + datetime.timedelta(days=9)).isoformat())
        self.assertContains(r, "La fecha de recepción no puede ser futura.")  # las dos reglas, juntas

    def test_la_recepcion_puede_ser_el_mismo_dia_del_plazo(self):
        self.post(fecha_recepcion=self.hoy.isoformat(), plazo=self.hoy.isoformat())
        self.assertEqual(Entregable.objects.get(titulo="Nuevo").fecha_recepcion, self.hoy)

    def test_una_fecha_mal_escrita_se_explica(self):
        self.rechaza("La fecha de recepción no es una fecha válida.", fecha_recepcion="31/02/2026")

    def test_el_id_tdr_tiene_un_largo_maximo(self):
        self.rechaza("El ID-TDR no puede superar los 50 caracteres.", id_tdr="X" * 51)

    def test_todos_los_faltantes_se_nombran_juntos(self):
        r = self.rechaza("No se pudo guardar. Revise lo siguiente:", id_tdr="", c_periodo="", fecha_recepcion="")
        for texto in ("Falta el ID-TDR.", "Falta la fecha de recepción.", "Falta completar el campo «Periodo»."):
            self.assertContains(r, texto)

    def test_si_llega_uno_de_los_dos_datos_de_recepcion_el_otro_es_obligatorio(self):
        datos = self.datos()
        del datos["fecha_recepcion"]
        self.client.force_login(self.s1)
        self.assertContains(self.client.post(reverse("entregable_nuevo"), datos), "Falta la fecha de recepción.")
        datos = self.datos()
        del datos["id_tdr"]
        self.assertContains(self.client.post(reverse("entregable_nuevo"), datos), "Falta el ID-TDR.")
        self.assertFalse(Entregable.objects.filter(titulo="Nuevo").exists())

    def test_una_peticion_sin_las_claves_de_recepcion_se_rechaza(self):
        # Son obligatorios SIEMPRE (validación del servidor), aunque la petición no traiga las claves.
        datos = self.datos()
        del datos["id_tdr"], datos["fecha_recepcion"]
        self.client.force_login(self.s1)
        r = self.client.post(reverse("entregable_nuevo"), datos)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "No se pudo guardar. Revise lo siguiente:")
        self.assertContains(r, "Falta el ID-TDR.")
        self.assertContains(r, "Falta la fecha de recepción.")
        self.assertFalse(Entregable.objects.filter(titulo="Nuevo").exists())

    def test_en_la_base_de_datos_siguen_admitiendo_vacio(self):
        # Los entregables anteriores al Sprint 2 no tienen ID-TDR: la base de datos lo admite (solo el formulario lo exige).
        Entregable.objects.filter(pk=self.e1.pk).update(id_tdr="", fecha_recepcion=None)
        self.e1.refresh_from_db()
        self.assertEqual((self.e1.id_tdr, self.e1.fecha_recepcion), ("", None))
        self.e1.titulo = "E1 editado"
        self.e1.save()  # editar no exige los datos de recepción
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.fecha_recepcion, None)

    def test_la_pantalla_pide_los_datos_de_recepcion_como_obligatorios(self):
        html = self.pagina().content.decode()
        self.assertIn("<h3>Recepción de la solicitud</h3>", html)
        self.assertRegex(html, r'<input type="text" name="id_tdr" maxlength="50" required[^>]*id="id_id_tdr">')
        self.assertRegex(html, rf'<input type="date" name="fecha_recepcion" value="{self.hoy.isoformat()}" required[^>]*>')
        for campo in ("id_id_tdr", "id_fecha_recepcion", "id_plazo"):
            self.assertIn(f'<label for="{campo}">', html)
        self.assertIn(f"Código del ticket: se asigna al guardar (p. ej. CT-{self.hoy.year}-00031).", html)
        # Orden de las secciones del wireframe: contrato, recepción (con el plazo), campos de la plantilla, responsables.
        posiciones = [html.index(t) for t in ('name="contrato"', 'name="id_tdr"', 'name="plazo"', 'name="c_periodo"',
                                               'name="junior_asignado"')]
        self.assertEqual(posiciones, sorted(posiciones))

    def test_muestra_el_cliente_y_la_linea_del_contrato_en_solo_lectura(self):
        html = self.pagina().content.decode()
        self.assertIn('data-reflejar', html)
        self.assertRegex(html, rf'<option value="{self.c1.pk}" data-cliente="Cliente Demo" data-linea="Digitalización">')
        self.assertIn('data-reflejo-de="id_contrato"', html)
        self.assertIn("(se toman del contrato, solo lectura)", html)
        # Al volver con errores, el contrato elegido ya muestra sus datos.
        r = self.post(id_tdr="")
        self.assertContains(r, 'Cliente: <strong data-dato="cliente">Cliente Demo</strong>')
        self.assertContains(r, 'Línea de servicio: <strong data-dato="linea">Digitalización</strong>')

    def test_un_contrato_sin_linea_lo_dice(self):
        self.c1.linea_servicio = None
        self.c1.save()
        self.assertContains(self.pagina(), 'data-linea="Sin asignar"')
        self.assertContains(self.post(id_tdr=""), 'Línea de servicio: <strong data-dato="linea">Sin asignar</strong>')

    def test_una_plantilla_mal_escrita_o_enorme_no_da_error_500(self):
        # Revisión de S2-H1 (S2-H1-H2-ajustes): «²» pasaba str.isdigit() y la consulta fallaba.
        self.client.force_login(self.s1)
        for valor in ("²", "abc", "1.5", "99999999999999999999999", "-1"):
            with self.subTest(valor=valor):
                r = self.client.get(reverse("entregable_nuevo"), {"plantilla": valor})
                self.assertEqual(r.status_code, 200)
                self.assertIsNone(r.context["form"])
                r = self.client.post(reverse("entregable_nuevo"), self.datos(plantilla=valor))
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, "Primero elija una plantilla de TDR.")
        self.assertFalse(Entregable.objects.filter(titulo="Nuevo").exists())

    def test_un_contrato_o_junior_con_id_enorme_se_rechaza_sin_error_500(self):
        r = self.post(contrato="99999999999999999999999", junior_asignado=str(2**63))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Elija un contrato vigente de la lista")
        self.assertFalse(Entregable.objects.filter(titulo="Nuevo").exists())

    def test_solo_se_ofrecen_los_contratos_propios(self):
        r = self.pagina()
        self.assertEqual(list(r.context["form"].fields["contrato"].queryset), [self.c1])  # s1 no ve el C2 de s2
        self.assertNotContains(r, "C2 ·")


class DetalleYListaConRecepcionTests(Base):
    def test_el_detalle_muestra_id_tdr_linea_recepcion_y_plazo(self):
        self.c1.linea_servicio = LineaServicio.objects.get(nombre="Custodia")
        self.c1.save()
        Entregable.objects.filter(pk=self.e1.pk).update(id_tdr="TDR-CD-001", fecha_recepcion=datetime.date(2026, 10, 30))
        self.client.force_login(self.j1)
        r = self.client.get(reverse("entregable_detalle", args=[self.e1.pk]))
        for texto in ("ID-TDR · Línea", "ID-TDR: TDR-CD-001", "Línea: Custodia", "Recepción · Plazo", "Recepción: 30/10/2026",
                      f"Plazo: <strong>{self.e1.plazo:%d/%m/%Y}</strong>"):
            self.assertContains(r, texto)

    def test_sin_id_tdr_ni_linea_lo_dice_en_texto(self):
        self.client.force_login(self.j1)
        r = self.client.get(reverse("entregable_detalle", args=[self.e1.pk]))
        self.assertContains(r, "ID-TDR: sin registrar")
        self.assertContains(r, "Línea: sin asignar")

    def test_la_lista_suma_las_columnas_codigo_e_id_tdr(self):
        Entregable.objects.filter(pk=self.e1.pk).update(id_tdr="TDR-CD-001")
        self.client.force_login(self.gerente)
        html = self.client.get(reverse("entregables")).content.decode()
        cabeceras = re.findall(r"<th>([^<]+)</th>", html)
        self.assertEqual(cabeceras[:5], ["Código", "Entregable", "Cliente", "Contrato", "ID-TDR"])
        fila = next(f for f in re.findall(r"<tr>.*?</tr>", html, flags=re.S) if ">E1</a>" in f)
        self.assertIn("TDR-CD-001", fila)
        sin = next(f for f in re.findall(r"<tr>.*?</tr>", html, flags=re.S) if ">E2</a>" in f)
        self.assertIn('<span class="sr-only">Sin ID-TDR</span>', sin)


class MigracionDeRellenoTests(Base):
    """La migración 0003 rellena el código y la recepción de lo que ya existía, y tiene reversa."""

    migracion = importlib.import_module("apps.entregables.migrations.0003_codigo_y_datos_de_recepcion")

    def como_antes_del_sprint_2(self, entregable, creado_en):
        Entregable.objects.filter(pk=entregable.pk).update(codigo=None, fecha_recepcion=None, creado_en=creado_en)

    def test_rellena_codigo_y_recepcion_con_la_fecha_local_de_creacion(self):
        self.como_antes_del_sprint_2(self.e1, datetime.datetime(2026, 1, 1, 3, 0, tzinfo=UTC))  # 31/12/2025 en Lima
        self.como_antes_del_sprint_2(self.e2, datetime.datetime(2026, 10, 5, 15, 0, tzinfo=UTC))
        self.migracion.rellenar(registro, None)
        self.e1.refresh_from_db()
        self.e2.refresh_from_db()
        self.assertEqual((self.e1.codigo, self.e1.fecha_recepcion), (f"CT-2025-{self.e1.pk:05d}", datetime.date(2025, 12, 31)))
        self.assertEqual((self.e2.codigo, self.e2.fecha_recepcion), (f"CT-2026-{self.e2.pk:05d}", datetime.date(2026, 10, 5)))

    def test_no_toca_lo_que_ya_tiene_codigo_ni_la_recepcion_registrada(self):
        Entregable.objects.filter(pk=self.e1.pk).update(codigo="CT-2020-00001", fecha_recepcion=datetime.date(2020, 1, 1))
        Entregable.objects.filter(pk=self.e2.pk).update(codigo=None, fecha_recepcion=datetime.date(2026, 9, 1))
        self.migracion.rellenar(registro, None)
        self.e1.refresh_from_db()
        self.e2.refresh_from_db()
        self.assertEqual((self.e1.codigo, self.e1.fecha_recepcion), ("CT-2020-00001", datetime.date(2020, 1, 1)))
        self.assertEqual(self.e2.fecha_recepcion, datetime.date(2026, 9, 1))
        self.assertRegex(self.e2.codigo, FORMATO)

    def test_la_reversa_los_vacia_y_se_puede_volver_a_aplicar(self):
        codigos = dict(Entregable.objects.values_list("pk", "codigo"))
        self.migracion.vaciar(registro, None)
        self.assertFalse(Entregable.objects.filter(codigo__isnull=False).exists())
        self.assertFalse(Entregable.objects.filter(fecha_recepcion__isnull=False).exists())
        self.migracion.rellenar(registro, None)
        self.assertEqual(dict(Entregable.objects.values_list("pk", "codigo")), codigos)

    def test_los_estados_guardados_no_cambian(self):
        # Solo cambian las etiquetas: la migración no toca la columna «estado».
        ops = [op for op in self.migracion.Migration.operations if getattr(op, "name", "") == "estado"]
        self.assertEqual([type(op).__name__ for op in ops], ["AlterField"])
        self.assertEqual([valor for valor, _ in ops[0].field.choices], list(E.values))


class SeedConRecepcionTests(MediaTemporal, TestCase):
    @classmethod
    def setUpTestData(cls):
        with mock.patch.object(ollama, "_post", sin_ollama):
            call_command("seed_demo", "--reset", stdout=io.StringIO())

    def test_todos_los_entregables_tienen_codigo_id_tdr_y_recepcion_coherentes(self):
        hoy = timezone.localdate()
        codigos = set()
        for e in Entregable.objects.all():
            with self.subTest(entregable=e.titulo):
                self.assertEqual(e.codigo, f"CT-{timezone.localtime(e.creado_en).year}-{e.pk:05d}")
                self.assertRegex(e.id_tdr, r"^TDR-[A-Z]{2,3}-\d{3}$")
                self.assertLessEqual(e.fecha_recepcion, min(hoy, e.plazo))
                codigos.add(e.codigo)
        self.assertEqual(len(codigos), Entregable.objects.count())

    def test_los_contratos_vigentes_tienen_linea_y_se_usan_las_cinco(self):
        vigentes = Contrato.objects.filter(activo=True).select_related("linea_servicio")
        self.assertFalse(vigentes.filter(linea_servicio__isnull=True).exists())
        self.assertEqual({c.linea_servicio.nombre for c in vigentes},
                         {"BPO", "Custodia", "Digitalización", "Banca", "Estado"})

    def test_los_avisos_de_la_demo_llevan_el_codigo(self):
        for n in Notificacion.objects.select_related("entregable"):
            self.assertIn(n.entregable.codigo, n.mensaje, n.mensaje)
