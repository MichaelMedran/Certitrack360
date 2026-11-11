"""SDD del Sprint 2, hito S2-H2 (base común) · §6.1: avisos sin entregable, con «enlace» (solo rutas internas) y tipos
nuevos. Criterio del hito: las notificaciones sin entregable se muestran y enlazan bien; las que tienen entregable siguen
enlazando a su detalle y la restricción «una alerta por umbral» conserva su sentido (ninguna prueba del Sprint 1 cambia)."""
import importlib
import re

from django.apps import apps as registro
from django.core.exceptions import ValidationError
from django.db import IntegrityError, migrations, transaction
from django.db.models import Q
from django.test import SimpleTestCase
from django.urls import reverse

from apps.alertas.enlaces import MENSAJE_ENLACE, es_enlace_interno, validar_enlace_interno
from apps.alertas.models import Notificacion
from apps.alertas.servicios import generar_alertas
from apps.entregables.models import Entregable
from apps.entregables.tests import Base

T = Notificacion.Tipo

INTERNOS = (
    "/",
    "/calendario/",
    "/entregables/?estado=EN_PROCESO&orden=plazo",
    "/entregables/5/#observaciones",
    "/lineas-servicio/",
    "/entregables/?q=acci%C3%B3n",  # lo que no es ASCII va codificado, como lo deja reverse()
)
# Direcciones externas y trucos de redirección abierta. Los dominios son de prueba (.invalid), nunca reales.
EXTERNOS = (
    "https://sitio-externo.invalid/fichas/3/",
    "http://sitio-externo.invalid",
    "//sitio-externo.invalid/fichas/3/",
    "///sitio-externo.invalid",
    "/\\sitio-externo.invalid",  # el navegador lee «\» como «/»: sería //sitio-externo.invalid
    "\\\\sitio-externo.invalid",
    "/\t/sitio-externo.invalid",  # el navegador descarta la tabulación y el salto de línea
    "/\n/sitio-externo.invalid",
    " /calendario/",
    "/calendario/ ",
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "data:text/html,hola",
    "mailto:persona@sitio-externo.invalid",
    "calendario/",  # relativa sin «/»: dependería de la página en la que se abre
    "sitio-externo.invalid",
    "/redirigir/?a=https://sitio-externo.invalid",  # tampoco un esquema dentro de la ruta
    "/calendario/\x00",
    "/calendário/",  # sin codificar
    '/calendario/"onmouseover="alert(1)',
    "/<script>",
)


def bloque(html, texto, etiqueta):
    """El <article> (lista de avisos) o el <li> (inicio) que contiene `texto`."""
    for parte in re.findall(rf"<{etiqueta}\b.*?</{etiqueta}>", html, flags=re.S):
        if texto in parte:
            return parte
    raise AssertionError(f"No se encontró «{texto}» en ningún <{etiqueta}>.")


def enlaces(html):
    return re.findall(r'href="([^"]*)"', html)


class EnlaceInternoTests(SimpleTestCase):
    def test_acepta_rutas_internas(self):
        for valor in INTERNOS:
            with self.subTest(valor=valor):
                self.assertTrue(es_enlace_interno(valor))
                validar_enlace_interno(valor)

    def test_vacio_es_un_aviso_sin_enlace(self):
        validar_enlace_interno("")
        self.assertFalse(es_enlace_interno(""))

    def test_rechaza_direcciones_externas_y_trucos_de_redireccion(self):
        for valor in EXTERNOS:
            with self.subTest(valor=valor):
                self.assertFalse(es_enlace_interno(valor))
                with self.assertRaises(ValidationError) as ctx:
                    validar_enlace_interno(valor)
                self.assertEqual(ctx.exception.messages, [MENSAJE_ENLACE])

    def test_lo_que_no_es_texto_no_es_un_enlace(self):
        for valor in (None, 3, b"/calendario/"):
            with self.subTest(valor=valor):
                self.assertFalse(es_enlace_interno(valor))

    def test_las_rutas_de_la_aplicacion_son_enlaces_validos(self):
        for nombre, args in (("calendario", []), ("entregable_detalle", [7]), ("notificaciones", []),
                             ("lineas_servicio", []), ("adm_editar", ["contratos", 3])):
            with self.subTest(ruta=nombre):
                self.assertTrue(es_enlace_interno(reverse(nombre, args=args)))


class ModeloTests(Base):
    def aviso(self, **datos):
        datos = {"usuario": self.j1, "tipo": T.FICHA, "mensaje": "Aviso de prueba.", **datos}
        return Notificacion.objects.create(**datos)

    def test_un_aviso_puede_no_tener_entregable_y_llevar_a_una_ruta_interna(self):
        n = self.aviso(enlace=reverse("calendario"))
        n.refresh_from_db()
        self.assertIsNone(n.entregable)
        self.assertEqual(n.destino, "/calendario/")

    def test_sin_entregable_ni_enlace_no_lleva_a_ninguna_parte(self):
        n = self.aviso()
        self.assertEqual((n.enlace, n.destino), ("", ""))

    def test_con_entregable_sigue_llevando_a_su_detalle(self):
        n = self.aviso(entregable=self.e1, tipo=T.ASIGNACION)
        self.assertEqual(n.enlace, "")
        self.assertEqual(n.destino, reverse("entregable_detalle", args=[self.e1.pk]))

    def test_si_tiene_enlace_lleva_a_el_aunque_sea_de_un_entregable(self):
        ruta = reverse("entregable_detalle", args=[self.e1.pk]) + "#observaciones"
        self.assertEqual(self.aviso(entregable=self.e1, tipo=T.CORRECCION, enlace=ruta).destino, ruta)

    def test_no_se_guarda_un_enlace_externo(self):
        for valor in EXTERNOS:
            with self.subTest(valor=valor), self.assertRaises(ValidationError) as ctx:
                self.aviso(enlace=valor)
            self.assertEqual(ctx.exception.messages, [MENSAJE_ENLACE])
        self.assertFalse(Notificacion.objects.exists())

    def test_tampoco_al_editarlo(self):
        n = self.aviso(enlace="/calendario/")
        n.enlace = "https://sitio-externo.invalid"
        for campos in (None, ["enlace"]):
            with self.subTest(update_fields=campos), self.assertRaises(ValidationError):
                n.save(update_fields=campos)
        n.refresh_from_db()
        self.assertEqual(n.enlace, "/calendario/")

    def test_el_formulario_del_modelo_explica_el_error_en_espanol(self):
        n = Notificacion(usuario=self.j1, tipo=T.FICHA, mensaje="x", enlace="https://sitio-externo.invalid")
        with self.assertRaises(ValidationError) as ctx:
            n.full_clean()
        self.assertEqual(ctx.exception.message_dict, {"enlace": [MENSAJE_ENLACE]})

    def test_la_base_de_datos_rechaza_lo_que_no_pasa_por_save(self):
        for valor in ("https://sitio-externo.invalid", "//sitio-externo.invalid", "calendario/"):
            with self.subTest(valor=valor):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Notificacion.objects.bulk_create([Notificacion(usuario=self.j1, tipo=T.FICHA, mensaje="x", enlace=valor)])
                n = self.aviso(enlace="/calendario/")
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Notificacion.objects.filter(pk=n.pk).update(enlace=valor)

    def test_un_enlace_que_no_es_interno_nunca_se_ofrece(self):
        # Pasa la restricción de la base de datos (empieza con una sola «/»), pero el navegador lo leería como //…
        sin_entregable, con_entregable = Notificacion.objects.bulk_create([
            Notificacion(usuario=self.j1, tipo=T.FICHA, mensaje="a", enlace="/\\sitio-externo.invalid"),
            Notificacion(usuario=self.j1, tipo=T.CORRECCION, mensaje="b", entregable=self.e1, enlace="/\\sitio-externo.invalid"),
        ])
        self.assertEqual(sin_entregable.destino, "")
        self.assertEqual(con_entregable.destino, reverse("entregable_detalle", args=[self.e1.pk]))

    def test_marcar_como_leido_no_se_bloquea_por_un_enlace_antiguo(self):
        (n,) = Notificacion.objects.bulk_create(
            [Notificacion(usuario=self.j1, tipo=T.FICHA, mensaje="antiguo", enlace="/\\sitio-externo.invalid")])
        self.client.force_login(self.j1)
        self.assertRedirects(self.client.post(reverse("notificacion_leer", args=[n.pk])), reverse("notificaciones"))
        n.refresh_from_db()
        self.assertTrue(n.leida)

    def test_tipos_nuevos_con_etiquetas_en_espanol(self):
        self.assertEqual(dict(T.choices), {
            "VENCIMIENTO": "Vencimiento", "OBSERVACION": "Observación", "ASIGNACION": "Asignación",
            "VERIFICACION": "Verificación", "CORRECCION": "Corrección", "ACTA": "Acta", "REASIGNACION": "Reasignación",
            "INCORPORACION": "Incorporación", "FICHA": "Ficha",
            # Sprint 3 (SDD del Sprint 3, §6.1)
            "URGENTE": "Urgente", "REPORTE": "Reporte", "CHECKLIST": "Checklist", "FACTURA": "Factura",
        })

    def test_todos_los_codigos_caben_y_se_guardan(self):
        self.assertLessEqual(max(len(v) for v in T.values), Notificacion._meta.get_field("tipo").max_length)
        for tipo in T.values:
            if tipo != T.VENCIMIENTO:
                self.aviso(tipo=tipo, mensaje=tipo)
        self.assertEqual(sorted(Notificacion.objects.values_list("tipo", flat=True)),
                         sorted(t for t in T.values if t != T.VENCIMIENTO))
        self.assertEqual(Notificacion.objects.get(tipo=T.INCORPORACION).get_tipo_display(), "Incorporación")

    def test_borrar_un_entregable_borra_sus_avisos_y_no_los_demas(self):
        self.aviso(entregable=self.e1, tipo=T.ASIGNACION, mensaje="del entregable")
        self.aviso(mensaje="sin entregable", enlace="/calendario/")
        Entregable.objects.get(pk=self.e1.pk).delete()
        self.assertEqual(list(Notificacion.objects.values_list("mensaje", flat=True)), ["sin entregable"])


class UnaAlertaPorUmbralTests(Base):
    """La restricción del Sprint 1 no cambia y sigue cubriendo todo aviso de vencimiento."""

    def test_la_restriccion_es_la_misma(self):
        (restriccion,) = [c for c in Notificacion._meta.constraints if c.name == "una_alerta_por_umbral"]
        self.assertEqual(restriccion.fields, ("usuario", "entregable", "umbral"))
        self.assertEqual(restriccion.condition, Q(tipo="VENCIMIENTO"))

    def test_sigue_impidiendo_un_segundo_aviso_del_mismo_umbral(self):
        Notificacion.objects.create(usuario=self.j1, entregable=self.e1, tipo=T.VENCIMIENTO, umbral=2, mensaje="uno")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Notificacion.objects.create(usuario=self.j1, entregable=self.e1, tipo=T.VENCIMIENTO, umbral=2, mensaje="dos")

    def test_un_aviso_de_vencimiento_siempre_es_de_un_entregable(self):
        for _ in range(2):  # sin esta regla, dos avisos sin entregable del mismo umbral no chocarían
            with self.assertRaises(IntegrityError), transaction.atomic():
                Notificacion.objects.create(usuario=self.j1, tipo=T.VENCIMIENTO, umbral=2, mensaje="sin entregable")
        n = Notificacion(usuario=self.j1, tipo=T.VENCIMIENTO, umbral=2, mensaje="x")
        with self.assertRaises(ValidationError) as ctx:
            n.full_clean()
        self.assertEqual(ctx.exception.messages, ["Un aviso de vencimiento siempre es de un entregable."])

    def test_los_demas_avisos_sin_entregable_se_pueden_repetir(self):
        for _ in range(2):
            Notificacion.objects.create(usuario=self.s1, tipo=T.FICHA, mensaje="Ficha por confirmar.", enlace="/calendario/")
        self.assertEqual(Notificacion.objects.filter(usuario=self.s1, tipo=T.FICHA).count(), 2)

    def test_la_tarea_de_alertas_convive_con_avisos_sin_entregable(self):
        otro = Notificacion.objects.create(usuario=self.j1, tipo=T.INCORPORACION, mensaje="Plan en curso.")
        e = self.nuevo(self.c1, self.j1, self.s1, "Pronto", dias=2)
        self.assertEqual(generar_alertas(self.hoy), 2)
        self.assertEqual(generar_alertas(self.hoy), 0)
        self.assertEqual(Notificacion.objects.filter(entregable=e, tipo=T.VENCIMIENTO).count(), 2)
        otro.refresh_from_db()
        self.assertEqual((otro.entregable, otro.leida, otro.mensaje), (None, False, "Plan en curso."))


class PantallaDeAvisosTests(Base):
    """Lista de avisos, inicio, insignia y marcado como leído con avisos sin entregable."""

    def setUp(self):
        self.con_enlace = Notificacion.objects.create(
            usuario=self.j1, tipo=T.INCORPORACION, mensaje="Revise el calendario de su primera semana.",
            enlace=reverse("calendario"))
        self.sin_enlace = Notificacion.objects.create(
            usuario=self.j1, tipo=T.REASIGNACION, mensaje="CT-2026-00099 «Informe ficticio» pasó a otra persona.")
        self.con_entregable = Notificacion.objects.create(
            usuario=self.j1, entregable=self.e1, tipo=T.ASIGNACION, mensaje="Se le asignó E1.")
        self.ajena = Notificacion.objects.create(usuario=self.j2, tipo=T.FICHA, mensaje="Aviso de otra persona.")

    def pagina(self, nombre="notificaciones", usuario=None):
        self.client.force_login(usuario or self.j1)
        return self.client.get(reverse(nombre)).content.decode()

    def test_el_aviso_con_enlace_lleva_a_su_ruta_y_la_ruta_responde(self):
        html = self.pagina()
        self.assertIn('<a href="/calendario/">Ver</a>', bloque(html, self.con_enlace.mensaje, "article"))
        self.assertEqual(self.client.get("/calendario/").status_code, 200)

    def test_el_aviso_sin_enlace_se_muestra_sin_ver_pero_se_puede_marcar(self):
        parte = bloque(self.pagina(), "pasó a otra persona", "article")
        self.assertNotIn("Ver</a>", parte)
        self.assertNotIn("href=", parte)
        self.assertIn(">Sin leer</span>", parte)
        self.assertIn(f'action="{reverse("notificacion_leer", args=[self.sin_enlace.pk])}"', parte)

    def test_los_avisos_con_entregable_siguen_enlazando_a_su_detalle(self):
        html = self.pagina()
        self.assertEqual(html.count(f'href="{reverse("entregable_detalle", args=[self.e1.pk])}">Ver</a>'), 1)
        self.assertEqual(html.count(">Ver</a>"), 2)  # el de la ruta interna y el del entregable

    def test_cada_aviso_dice_su_tipo_y_su_estado_con_texto(self):
        html = self.pagina()
        for tipo in ("Incorporación", "Reasignación", "Asignación"):
            self.assertIn(f'<span class="etiqueta">{tipo}</span>', html)
        self.assertEqual(html.count(">Sin leer</span>"), 3)

    def test_cada_persona_ve_solo_los_suyos(self):
        self.assertNotIn(self.ajena.mensaje, self.pagina())
        html = self.pagina(usuario=self.j2)
        self.assertIn(self.ajena.mensaje, html)
        self.assertNotIn(self.con_enlace.mensaje, html)

    def test_el_inicio_los_muestra_con_su_enlace_o_sin_el(self):
        html = self.pagina("inicio")
        self.assertIn('<a href="/calendario/">Ver</a>', bloque(html, self.con_enlace.mensaje, "li"))
        self.assertNotIn("href=", bloque(html, "pasó a otra persona", "li"))
        self.assertIn(f'href="{reverse("entregable_detalle", args=[self.e1.pk])}">Ver</a>', bloque(html, "Se le asignó E1.", "li"))

    def test_la_insignia_cuenta_tambien_los_avisos_sin_entregable(self):
        self.assertIn('<span class="insignia" aria-label="3 sin leer">3</span>', self.pagina("inicio"))
        self.assertIn('aria-label="1 sin leer"', self.pagina("inicio", self.j2))

    def test_marcar_como_leido_un_aviso_sin_entregable(self):
        self.client.force_login(self.j1)
        r = self.client.post(reverse("notificacion_leer", args=[self.sin_enlace.pk]))
        self.assertRedirects(r, reverse("notificaciones"))
        self.sin_enlace.refresh_from_db()
        self.con_enlace.refresh_from_db()
        self.assertEqual((self.sin_enlace.leida, self.con_enlace.leida), (True, False))
        html = self.pagina()
        self.assertIn('aria-label="2 sin leer"', html)
        self.assertIn(">Leída</span>", bloque(html, "pasó a otra persona", "article"))

    def test_marcar_todos_incluye_los_sin_entregable_y_solo_los_propios(self):
        self.client.force_login(self.j1)
        self.client.post(reverse("notificaciones_leidas"))
        self.assertFalse(Notificacion.objects.filter(usuario=self.j1, leida=False).exists())
        self.ajena.refresh_from_db()
        self.assertFalse(self.ajena.leida)
        self.assertNotIn("insignia", self.pagina())

    def test_nadie_marca_el_aviso_de_otra_persona(self):
        self.client.force_login(self.j2)  # junior de otro contrato
        self.assertEqual(self.client.post(reverse("notificacion_leer", args=[self.sin_enlace.pk])).status_code, 404)
        self.client.force_login(self.j1)
        self.assertEqual(self.client.post(reverse("notificacion_leer", args=[self.ajena.pk])).status_code, 404)
        self.assertFalse(Notificacion.objects.filter(leida=True).exists())

    def test_el_enlace_va_escapado_en_el_html_y_funciona(self):
        ruta = "/entregables/?estado=EN_PROCESO&orden=plazo"
        Notificacion.objects.create(usuario=self.j1, tipo=T.CORRECCION, mensaje="Con filtros.", enlace=ruta)
        parte = bloque(self.pagina(), "Con filtros.", "article")
        self.assertIn('href="/entregables/?estado=EN_PROCESO&amp;orden=plazo">Ver</a>', parte)
        self.assertEqual(self.client.get(ruta).status_code, 200)

    def test_un_enlace_externo_que_llegara_a_la_base_nunca_se_muestra(self):
        Notificacion.objects.bulk_create([
            Notificacion(usuario=self.j1, tipo=T.FICHA, mensaje="Enlace antiguo.", enlace="/\\sitio-externo.invalid")])
        for nombre, etiqueta in (("notificaciones", "article"), ("inicio", "li")):
            with self.subTest(pantalla=nombre):
                html = self.pagina(nombre)
                self.assertNotIn("Ver</a>", bloque(html, "Enlace antiguo.", etiqueta))
                self.assertFalse([e for e in enlaces(html) if "sitio-externo" in e])


class CuatroRolesTests(Base):
    """Cada rol recibe y abre sus avisos sin entregable; nadie ve los de otra persona del mismo rol."""

    def test_cada_rol_ve_y_abre_los_suyos(self):
        destinos = {self.j1: reverse("calendario"), self.s1: reverse("calendario"),
                    self.gerente: reverse("lineas_servicio"), self.admin: reverse("lineas_servicio")}
        for usuario, ruta in destinos.items():
            Notificacion.objects.create(usuario=usuario, tipo=T.FICHA, mensaje=f"Aviso para {usuario.username}.", enlace=ruta)
        for usuario, ruta in destinos.items():
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                html = self.client.get(reverse("notificaciones")).content.decode()
                self.assertIn(f'<a href="{ruta}">Ver</a>', bloque(html, f"Aviso para {usuario.username}.", "article"))
                inicio = self.client.get(reverse("inicio")).content.decode()
                self.assertIn(f'<a href="{ruta}">Ver</a>', bloque(inicio, f"Aviso para {usuario.username}.", "li"))
                self.assertEqual(self.client.get(ruta).status_code, 200)
                for otro in destinos:
                    if otro != usuario:
                        self.assertNotIn(f"Aviso para {otro.username}.", html)

    def test_los_del_mismo_rol_ajenos_no_los_ven_ni_los_marcan(self):
        for duenio, ajeno in ((self.j1, self.j2), (self.s1, self.s2)):
            with self.subTest(duenio=duenio.username):
                n = Notificacion.objects.create(usuario=duenio, tipo=T.REASIGNACION, mensaje=f"Solo de {duenio.username}.")
                self.client.force_login(ajeno)
                self.assertNotContains(self.client.get(reverse("notificaciones")), n.mensaje)
                self.assertNotContains(self.client.get(reverse("inicio")), n.mensaje)
                self.assertEqual(self.client.post(reverse("notificacion_leer", args=[n.pk])).status_code, 404)
                n.refresh_from_db()
                self.assertFalse(n.leida)


class PantallasConAvisosSinEntregableTests(Base):
    """Ninguna pantalla supone que todo aviso tiene entregable (la insignia está en todas)."""

    def setUp(self):
        for usuario in (self.j1, self.gerente):
            Notificacion.objects.create(usuario=usuario, tipo=T.FICHA, mensaje="Sin entregable ni enlace.")
            Notificacion.objects.create(usuario=usuario, tipo=T.INCORPORACION, mensaje="Con enlace.", enlace="/calendario/")

    def test_todas_las_pantallas_responden(self):
        comunes = [reverse(n) for n in ("inicio", "tablero", "entregables", "calendario", "calendario_eventos",
                                        "notificaciones", "asistente")]
        comunes.append(reverse("entregable_detalle", args=[self.e1.pk]))
        gestion = [reverse(n) for n in ("consolidado", "lineas_servicio", "entregable_nuevo")]
        gestion.append(reverse("adm_lista", args=["clientes"]))  # «Gestión» lleva a esta primera pestaña
        for usuario, rutas in ((self.j1, comunes), (self.gerente, comunes + gestion)):
            self.client.force_login(usuario)
            for ruta in rutas:
                with self.subTest(usuario=usuario.username, ruta=ruta):
                    r = self.client.get(ruta)
                    self.assertEqual(r.status_code, 200)
                    if r["Content-Type"].startswith("text/html"):
                        self.assertContains(r, 'aria-label="2 sin leer"')


class MigracionDeAvisosTests(Base):
    """La migración 0004 es aditiva, no toca «una alerta por umbral» y su reversa deja solo lo que el Sprint 1 admite."""

    migracion = importlib.import_module("apps.alertas.migrations.0004_avisos_sin_entregable_y_enlace")

    def test_es_aditiva_y_no_toca_la_restriccion_de_umbral(self):
        ops = self.migracion.Migration.operations
        self.assertEqual({type(op).__name__ for op in ops}, {"AlterField", "RunPython", "AddField", "AddConstraint"})
        nombres = {getattr(op, "name", "") for op in ops} | {getattr(getattr(op, "constraint", None), "name", "") for op in ops}
        self.assertNotIn("una_alerta_por_umbral", nombres)
        entregable = next(op for op in ops if getattr(op, "name", "") == "entregable")
        self.assertTrue(entregable.field.null)
        enlace = next(op for op in ops if getattr(op, "name", "") == "enlace")
        self.assertEqual(enlace.field.default, "")

    def test_hacia_adelante_no_cambia_ningun_dato(self):
        (paso,) = [op for op in self.migracion.Migration.operations if isinstance(op, migrations.RunPython)]
        self.assertIs(paso.code, migrations.RunPython.noop)
        self.assertTrue(paso.reversible)

    def test_la_reversa_borra_solo_lo_que_el_esquema_del_sprint_1_no_admite(self):
        Notificacion.objects.all().delete()
        del_sprint_1 = [
            Notificacion.objects.create(usuario=self.j1, entregable=self.e1, tipo=tipo, mensaje=tipo)
            for tipo in (T.ASIGNACION, T.OBSERVACION, T.VERIFICACION)
        ]
        del_sprint_1.append(Notificacion.objects.create(
            usuario=self.j1, entregable=self.e1, tipo=T.VENCIMIENTO, umbral=2, mensaje="VENCIMIENTO"))
        Notificacion.objects.create(usuario=self.s1, tipo=T.FICHA, mensaje="sin entregable", enlace="/calendario/")
        Notificacion.objects.create(usuario=self.s1, tipo=T.ASIGNACION, mensaje="tipo viejo sin entregable")
        Notificacion.objects.create(usuario=self.s1, entregable=self.e1, tipo=T.CORRECCION, mensaje="tipo nuevo")
        Notificacion.objects.create(usuario=self.s1, entregable=self.e1, tipo=T.INCORPORACION, mensaje="código de 13 letras")
        self.migracion.quitar_avisos_que_el_sprint_1_no_admite(registro, None)
        self.assertEqual(set(Notificacion.objects.values_list("pk", flat=True)), {n.pk for n in del_sprint_1})
