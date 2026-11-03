"""SDD del Sprint 2, hito S2-H4 · RF-28 y RF-29 (casos 19, 20 y 21b): versiones vigentes, restaurar, versión enviada bloqueada,
entrega con cargo de recepción, acta de conformidad, reapertura por acta observada, alerta de acta pendiente e historial."""
import datetime
import os
import re
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import F
from django.test import Client, override_settings
from django.urls import reverse

from apps.alertas import programador
from apps.alertas.models import Notificacion
from apps.alertas.servicios import generar_alertas_acta
from apps.clientes.forms import PlantillaForm
from apps.clientes.models import Cliente, Contrato
from apps.cuentas.models import Usuario
from apps.entregables import adjuntos, entregas, servicios
from apps.entregables import observaciones as obs_servicio
from apps.entregables.models import Adjunto, Entrega, Entregable, Observacion
from apps.entregables.tests import Base
from apps.entregables.tipos import TIPOS_DE_ENTREGA, TIPOS_DE_SUBIDA, TipoAdjunto
from apps.entregables.visibilidad import entregables_visibles

E = Entregable.Estado
A = Entrega.ActaEstado
HX = {"HTTP_HX_REQUEST": "true"}


def archivo(nombre="documento.pdf", contenido=b"%PDF-1.4 ficticio"):
    return SimpleUploadedFile(nombre, contenido, content_type="application/pdf")


def archivos_en_disco():
    return sorted(os.path.join(raiz, f) for raiz, _, fs in os.walk(settings.MEDIA_ROOT) for f in fs)


class EntregasBase(Base):
    def aprobado(self, titulo="Aprobado", versiones=2, contrato=None, junior=None, senior=None):
        e = self.nuevo(contrato or self.c1, junior or self.j1, senior or self.s1, titulo, estado=E.LISTO_PARA_ENTREGA)
        for n in range(1, versiones + 1):
            adjuntos.crear_adjunto(e, e.senior_revisor, archivo(f"final{n}.pdf", f"%PDF contenido v{n}".encode()),
                                   "VERSION_FINAL", f"versión {n}")
        return e

    def registrar(self, e, usuario=None, **cambios):
        valores = {"fecha_entrega": self.hoy, "medio": "CORREO", "cargo": archivo("cargo.pdf", b"%PDF cargo")}
        valores.update(cambios)
        return entregas.registrar(e, usuario or self.s1, **valores)

    def entregado(self, titulo="Entregado", acta=None, **kw):
        e = self.aprobado(titulo, **kw)
        entrega = self.registrar(e)
        if acta:
            entregas.registrar_acta(entrega, self.s1, acta, archivo("acta.pdf", b"%PDF acta"))
            entrega.refresh_from_db()
        return e, entrega

    def reabierto(self, titulo="Reabierto"):
        e, entrega = self.entregado(titulo, acta=A.OBSERVADA)
        servicios.mover(e, E.EN_PROCESO, self.s1, tipo_error="CONTENIDO", descripcion="El cliente pidió ajustar el anexo")
        return e, entrega

    def datos_http(self, e, **cambios):
        datos = {"fecha_entrega": f"{self.hoy:%Y-%m-%d}", "medio": "MESA_DE_PARTES", "cargo": archivo("cargo.pdf", b"%PDF cargo"),
                 "version_enviada": adjuntos.vigente(e, "VERSION_FINAL").pk if adjuntos.vigente(e, "VERSION_FINAL") else "",
                 "comentario": ""}
        datos.update(cambios)
        return datos


# ------------------------------------------------------------------ RF-28: versiones


class VersionVigenteTests(EntregasBase):
    def test_la_vigente_es_la_de_numero_mas_alto(self):
        e = self.aprobado()
        self.assertEqual(adjuntos.vigente(e, "VERSION_FINAL").version, 2)
        self.assertIsNone(adjuntos.vigente(e, "BORRADOR"))

    def test_una_version_eliminada_deja_vigente_la_anterior_de_mayor_numero(self):
        e = self.aprobado(versiones=3)
        adjuntos.eliminar(adjuntos.vigente(e, "VERSION_FINAL"), self.gerente)
        self.assertEqual(adjuntos.vigente(e, "VERSION_FINAL").version, 2)

    def test_el_detalle_destaca_la_vigente_y_agrupa_las_anteriores(self):
        e = self.aprobado()
        self.client.force_login(self.s1)
        html = self.client.get(reverse("entregable_detalle", args=[e.pk])).content.decode()
        self.assertIn("Vigente · v2", html)
        self.assertNotIn("Vigente · v1", html)
        self.assertIn("Ver versiones anteriores de «Versión final» (1)", html)

    def test_el_comentario_es_obligatorio_en_el_formulario_de_subida(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Sube")
        self.client.force_login(self.j1)
        url = reverse("adjunto_subir", args=[e.pk])
        for comentario in (None, "", "   "):
            with self.subTest(comentario=comentario):
                datos = {"tipo": "BORRADOR", "archivo": archivo()}
                if comentario is not None:
                    datos["comentario"] = comentario
                r = self.client.post(url, datos, follow=True)
                self.assertContains(r, "Escriba el comentario del cambio")
        self.assertFalse(e.adjuntos.exists())
        r = self.client.post(url, {"tipo": "BORRADOR", "archivo": archivo(), "comentario": " Primera versión "})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(e.adjuntos.get().comentario, "Primera versión")

    def test_la_funcion_de_servicio_sigue_aceptando_el_comentario_vacio(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Seed")
        self.assertEqual(adjuntos.subir(e, self.j1, archivo(), "BORRADOR").comentario, "")

    def test_el_formulario_de_subida_no_ofrece_el_cargo_ni_el_acta(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Tipos")
        self.client.force_login(self.s1)
        html = self.client.get(reverse("entregable_detalle", args=[e.pk])).content.decode()
        self.assertNotIn('value="CARGO_RECEPCION"', html)
        self.assertNotIn('value="ACTA_CONFORMIDAD"', html)
        for tipo in ("CARGO_RECEPCION", "ACTA_CONFORMIDAD"):
            r = self.client.post(reverse("adjunto_subir", args=[e.pk]),
                                 {"tipo": tipo, "archivo": archivo(), "comentario": "x"}, follow=True)
            self.assertContains(r, "Elija un tipo de adjunto válido")
            with self.assertRaises(ValidationError):
                adjuntos.subir(e, self.s1, archivo(), tipo)
        self.assertFalse(e.adjuntos.exists())


class TiposNuevosNoSonRequeridosTests(EntregasBase):
    def test_los_tipos_nuevos_no_se_ofrecen_como_adjuntos_requeridos_de_la_plantilla(self):
        valores = [v for v, _ in PlantillaForm().fields["adjuntos_requeridos"].choices]
        self.assertEqual(valores, ["TDR", "BORRADOR", "VERSION_FINAL", "EVIDENCIA", "OTRO"])
        self.assertEqual({v for v, _ in TIPOS_DE_SUBIDA}, set(TipoAdjunto.values) - {t.value for t in TIPOS_DE_ENTREGA})

    def test_el_cargo_y_el_acta_no_alteran_los_faltantes_ni_la_numeracion_de_versiones(self):
        from apps.clientes.models import PlantillaTDR

        PlantillaTDR.objects.filter(pk=self.plantilla.pk).update(adjuntos_requeridos=["VERSION_FINAL"])
        e = self.aprobado(versiones=1)
        self.assertEqual(adjuntos.faltantes_requeridos(e), [])
        entrega = self.registrar(e)
        entregas.registrar_acta(entrega, self.s1, A.RECIBIDA, archivo("acta.pdf"))
        self.assertEqual(adjuntos.faltantes_requeridos(e), [])
        self.assertEqual(adjuntos.vigente(e, "VERSION_FINAL").version, 1)
        self.assertEqual((adjuntos.vigente(e, "CARGO_RECEPCION").version, adjuntos.vigente(e, "ACTA_CONFORMIDAD").version), (1, 1))


class RestaurarTests(EntregasBase):
    def setUp(self):
        self.e = self.aprobado()
        self.v1 = self.e.adjuntos.get(tipo="VERSION_FINAL", version=1)
        self.v2 = self.e.adjuntos.get(tipo="VERSION_FINAL", version=2)

    def restaurar(self, usuario, adjunto=None, **extra):
        self.client.force_login(usuario)
        return self.client.post(reverse("adjunto_restaurar", args=[(adjunto or self.v1).pk]), **extra)

    def test_restaurar_crea_una_version_nueva_que_copia_el_archivo_sin_reescribir_ninguna(self):
        antes = {a.pk: (a.version, a.archivo.name, a.comentario, a.nombre_original) for a in self.e.adjuntos.all()}
        nueva = adjuntos.restaurar(self.v1, self.s1)
        self.assertEqual((nueva.tipo, nueva.version), ("VERSION_FINAL", 3))
        self.assertEqual(nueva.restaurado_desde, self.v1)
        self.assertEqual(nueva.comentario, "Restaurada desde la v1")
        self.assertEqual(nueva.nombre_original, self.v1.nombre_original)
        self.assertNotEqual(nueva.archivo.name, self.v1.archivo.name)
        with nueva.archivo.open("rb") as copia, self.v1.archivo.open("rb") as origen:
            self.assertEqual(copia.read(), origen.read())
        despues = {a.pk: (a.version, a.archivo.name, a.comentario, a.nombre_original) for a in self.e.adjuntos.exclude(pk=nueva.pk)}
        self.assertEqual(antes, despues)  # ninguna versión existente se reescribió
        self.assertEqual(adjuntos.vigente(self.e, "VERSION_FINAL"), nueva)
        h = self.e.historial.order_by("-id").first()
        self.assertEqual(h.descripcion, "Restauró Versión final v1 como vigente (nueva v3, final1.pdf)")
        self.assertEqual(h.usuario, self.s1)

    def test_restaurar_varias_veces_sigue_creando_versiones_nuevas(self):
        adjuntos.restaurar(self.v1, self.s1)
        nueva = adjuntos.restaurar(self.v2, self.gerente)
        self.assertEqual(nueva.version, 4)
        self.assertEqual(nueva.restaurado_desde, self.v2)
        self.assertEqual(self.e.adjuntos.filter(tipo="VERSION_FINAL").count(), 4)

    def test_http_senior_del_entregable_gerente_y_admin_restauran(self):
        for n, usuario in enumerate((self.s1, self.gerente, self.admin), start=3):
            with self.subTest(usuario=usuario.username):
                r = self.restaurar(usuario)
                self.assertRedirects(r, reverse("entregable_detalle", args=[self.e.pk]) + "#adjuntos", fetch_redirect_response=False)
                self.assertEqual(adjuntos.vigente(self.e, "VERSION_FINAL").version, n)

    def test_http_mensaje_de_exito_y_de_error(self):
        r = self.restaurar(self.s1, follow=True)
        self.assertContains(r, "Se restauró la v1 de Versión final: ahora es la v3")
        r = self.restaurar(self.s1, adjunto=adjuntos.vigente(self.e, "VERSION_FINAL"), follow=True)
        self.assertContains(r, "ya es la versión vigente")
        self.assertEqual(self.e.adjuntos.filter(tipo="VERSION_FINAL").count(), 3)

    def test_el_junior_no_restaura_ni_el_ajeno_ve_el_adjunto(self):
        self.assertEqual(self.restaurar(self.j1).status_code, 403)
        self.assertEqual(self.restaurar(self.s2).status_code, 404)  # senior de otro contrato: no existe para él
        self.assertEqual(self.restaurar(self.j2).status_code, 404)
        self.assertEqual(self.e.adjuntos.count(), 2)
        for usuario in (self.j1, self.s2):
            with self.assertRaises(PermissionDenied):
                adjuntos.restaurar(self.v1, usuario)

    def test_solo_post_con_sesion_y_con_csrf(self):
        url = reverse("adjunto_restaurar", args=[self.v1.pk])
        self.assertEqual(self.client.post(url).status_code, 302)  # sin sesión: al login
        self.client.force_login(self.s1)
        self.assertEqual(self.client.get(url).status_code, 405)
        estricto = Client(enforce_csrf_checks=True)
        estricto.force_login(self.s1)
        self.assertEqual(estricto.post(url).status_code, 403)
        self.assertEqual(self.e.adjuntos.count(), 2)

    def test_no_se_restaura_la_vigente_ni_el_cargo_ni_el_acta(self):
        with self.assertRaises(ValidationError):
            adjuntos.restaurar(self.v2, self.s1)
        entrega = self.registrar(self.e)
        entregas.registrar_acta(entrega, self.s1, A.RECIBIDA, archivo("acta.pdf"))
        for tipo in ("CARGO_RECEPCION", "ACTA_CONFORMIDAD"):
            with self.subTest(tipo=tipo), self.assertRaises(ValidationError):
                adjuntos.restaurar(adjuntos.vigente(self.e, tipo), self.s1)

    def test_un_archivo_que_ya_no_esta_en_disco_se_avisa_sin_crear_nada(self):
        os.remove(self.v1.archivo.path)
        r = self.restaurar(self.s1, follow=True)
        self.assertContains(r, "no se encuentra en el servidor")
        self.assertEqual(self.e.adjuntos.count(), 2)

    def test_el_detalle_ofrece_restaurar_solo_en_las_anteriores_y_solo_a_quien_puede(self):
        url = reverse("entregable_detalle", args=[self.e.pk])
        for usuario in (self.s1, self.gerente, self.admin):
            self.client.force_login(usuario)
            html = self.client.get(url).content.decode()
            self.assertEqual(html.count("Restaurar como vigente"), 1, usuario.username)
            self.assertIn(reverse("adjunto_restaurar", args=[self.v1.pk]), html)
            self.assertNotIn(reverse("adjunto_restaurar", args=[self.v2.pk]), html)
        self.client.force_login(self.j1)
        self.assertNotIn("Restaurar como vigente", self.client.get(url).content.decode())


# ------------------------------------------------------------------ RF-28: bloqueo de la versión enviada


class VersionBloqueadaTests(EntregasBase):
    def setUp(self):
        self.e, self.entrega = self.entregado()
        self.enviada = self.entrega.version_enviada

    def eliminar(self, usuario, adjunto):
        self.client.force_login(usuario)
        return self.client.post(reverse("adjunto_eliminar", args=[adjunto.pk]))

    def test_la_version_enviada_queda_bloqueada_y_las_demas_no(self):
        self.assertEqual(self.enviada.version, 2)
        self.assertTrue(Adjunto.objects.get(pk=self.enviada.pk).bloqueado)
        self.assertFalse(self.e.adjuntos.get(tipo="VERSION_FINAL", version=1).bloqueado)

    def test_eliminar_la_enviada_responde_403_con_el_motivo_incluso_al_gerente_y_al_admin(self):
        for usuario in (self.gerente, self.admin):
            with self.subTest(usuario=usuario.username):
                r = self.eliminar(usuario, self.enviada)
                self.assertContains(r, "Esta versión está bloqueada", status_code=403)
                self.assertContains(r, "no se puede eliminar", status_code=403)
        self.assertTrue(Adjunto.objects.filter(pk=self.enviada.pk).exists())
        self.assertTrue(Adjunto.objects.filter(pk=self.enviada.pk).get().archivo.storage.exists(self.enviada.archivo.name))

    def test_el_servicio_tambien_lo_impide(self):
        with self.assertRaises(PermissionDenied) as ctx:
            adjuntos.eliminar(self.enviada, self.gerente)
        self.assertEqual(str(ctx.exception), adjuntos.MOTIVO_BLOQUEO)

    def test_el_cargo_queda_bloqueado_tambien(self):
        self.assertTrue(self.entrega.cargo.bloqueado)
        self.assertEqual(self.eliminar(self.gerente, self.entrega.cargo).status_code, 403)
        self.assertTrue(Adjunto.objects.filter(pk=self.entrega.cargo_id).exists())

    def test_una_version_no_enviada_sigue_pudiendo_eliminarse_por_el_gerente(self):
        v1 = self.e.adjuntos.get(tipo="VERSION_FINAL", version=1)
        self.assertEqual(self.eliminar(self.gerente, v1).status_code, 302)
        self.assertFalse(Adjunto.objects.filter(pk=v1.pk).exists())

    def test_el_detalle_marca_la_bloqueada_y_no_ofrece_eliminarla(self):
        self.client.force_login(self.gerente)
        html = self.client.get(reverse("entregable_detalle", args=[self.e.pk])).content.decode()
        self.assertIn("Bloqueada", html)
        self.assertNotIn(reverse("adjunto_eliminar", args=[self.enviada.pk]), html)
        self.assertIn(reverse("adjunto_eliminar", args=[self.e.adjuntos.get(tipo="VERSION_FINAL", version=1).pk]), html)

    def test_el_panel_tecnico_tampoco_elimina_una_version_bloqueada(self):
        from apps.entregables.admin import AdjuntoAdmin
        from django.contrib import admin as dj_admin

        modelo = AdjuntoAdmin(Adjunto, dj_admin.site)
        peticion = mock.Mock(user=self.admin)
        peticion.user.has_perm = lambda *a, **k: True
        self.assertFalse(modelo.has_delete_permission(peticion, Adjunto.objects.get(pk=self.enviada.pk)))
        self.assertTrue(modelo.has_delete_permission(peticion, self.e.adjuntos.get(tipo="VERSION_FINAL", version=1)))

    def test_no_se_borra_un_adjunto_que_una_entrega_referencia_ni_por_la_base(self):
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            Adjunto.objects.filter(pk=self.enviada.pk).delete()


# ------------------------------------------------------------------ RF-29: entregar


class ServicioDeEntregaTests(EntregasBase):
    def test_no_se_pasa_a_entregado_sin_cargo_por_ningun_camino(self):
        e = self.aprobado()
        with self.assertRaises(ValidationError) as ctx:
            servicios.mover(e, E.HECHO, self.s1)
        self.assertIn("falta el cargo de recepción", ctx.exception.messages[0])
        e.refresh_from_db()
        self.assertEqual(e.estado, E.LISTO_PARA_ENTREGA)
        self.assertFalse(e.entregas.exists())

    def test_registrar_hace_todo_en_una_transaccion(self):
        e = self.aprobado()
        v2 = adjuntos.vigente(e, "VERSION_FINAL")
        entrega = self.registrar(e, medio="MESA_DE_PARTES", comentario="Entregado en ventanilla")
        e.refresh_from_db()
        self.assertEqual(e.estado, E.HECHO)
        self.assertEqual((entrega.numero, entrega.acta_estado, entrega.acta), (1, A.PENDIENTE, None))
        self.assertEqual((entrega.fecha_entrega, entrega.medio, entrega.registrada_por), (self.hoy, "MESA_DE_PARTES", self.s1))
        self.assertEqual((entrega.cargo.tipo, entrega.cargo.version, entrega.cargo.comentario),
                         ("CARGO_RECEPCION", 1, "Entregado en ventanilla"))
        self.assertTrue(entrega.cargo.bloqueado)
        self.assertEqual(entrega.version_enviada, v2)
        self.assertTrue(Adjunto.objects.get(pk=v2.pk).bloqueado)
        self.assertEqual(entrega.cierre.estado_nuevo, E.HECHO)
        textos = [h.descripcion for h in e.historial.order_by("id")]
        self.assertTrue(any(t.startswith("Registró el cargo de recepción de la entrega n.º 1: v1 (cargo.pdf, Mesa de partes,") for t in textos))
        self.assertEqual(textos[-1], "Estado: Aprobado → Entregado (Entrega n.º 1 (Mesa de partes))")

    def test_la_version_indicada_es_la_que_se_bloquea(self):
        e = self.aprobado()
        v1 = e.adjuntos.get(tipo="VERSION_FINAL", version=1)
        entrega = self.registrar(e, version_enviada=v1)
        self.assertEqual(entrega.version_enviada, v1)
        self.assertTrue(Adjunto.objects.get(pk=v1.pk).bloqueado)
        self.assertFalse(e.adjuntos.get(tipo="VERSION_FINAL", version=2).bloqueado)

    def test_se_puede_indicar_otro_tipo_de_adjunto_del_mismo_entregable_por_id(self):
        e = self.aprobado(versiones=0)
        borrador = adjuntos.crear_adjunto(e, self.s1, archivo(), "BORRADOR", "único")
        self.assertEqual(self.registrar(e, version_enviada=borrador.pk).version_enviada, borrador)

    def test_la_version_debe_ser_del_mismo_entregable_y_no_el_cargo_ni_el_acta(self):
        e, otro = self.aprobado(), self.aprobado("Otro")
        ajena = adjuntos.vigente(otro, "VERSION_FINAL")
        cargo_ajeno = self.registrar(otro).cargo
        for version in (ajena, ajena.pk, cargo_ajeno, 99999, "abc"):
            with self.subTest(version=version), self.assertRaises(ValidationError) as ctx:
                self.registrar(e, version_enviada=version)
            self.assertIn("debe ser un adjunto de este mismo entregable", ctx.exception.messages[0])
        e.refresh_from_db()
        self.assertEqual((e.estado, e.entregas.count()), (E.LISTO_PARA_ENTREGA, 0))

    def test_sin_version_final_ni_version_indicada_se_pide_una(self):
        e = self.aprobado(versiones=0)
        with self.assertRaises(ValidationError) as ctx:
            self.registrar(e)
        self.assertIn("Falta la versión enviada", ctx.exception.messages[0])

    def test_la_fecha_no_puede_ser_futura_ni_faltar_y_el_medio_es_obligatorio(self):
        e = self.aprobado()
        casos = [({"fecha_entrega": self.hoy + datetime.timedelta(days=1)}, "no puede ser futura"),
                 ({"fecha_entrega": None}, "Falta la fecha de entrega"),
                 ({"medio": "PALOMA"}, "Elija el medio de entrega"), ({"medio": ""}, "Elija el medio de entrega"),
                 ({"cargo": None}, "Falta el cargo de recepción")]
        for cambios, texto in casos:
            with self.subTest(cambios=cambios), self.assertRaises(ValidationError) as ctx:
                self.registrar(e, **cambios)
            self.assertIn(texto, " ".join(ctx.exception.messages))
        self.assertEqual(self.registrar(e, fecha_entrega=self.hoy - datetime.timedelta(days=3)).fecha_entrega,
                         self.hoy - datetime.timedelta(days=3))  # una fecha pasada vale

    def test_se_acumulan_los_errores_para_decir_todo_lo_que_falta(self):
        e = self.aprobado()
        with self.assertRaises(ValidationError) as ctx:
            self.registrar(e, fecha_entrega=self.hoy + datetime.timedelta(days=2), medio="", cargo=None)
        self.assertEqual(len(ctx.exception.messages), 3)

    def test_el_cargo_pasa_por_la_validacion_comun_de_archivos(self):
        e = self.aprobado()
        for nombre, contenido, texto in (("cargo.exe", b"x", "no es de un tipo permitido"), ("cargo.pdf", b"", "está vacío")):
            with self.subTest(nombre=nombre), self.assertRaises(ValidationError) as ctx:
                self.registrar(e, cargo=SimpleUploadedFile(nombre, contenido))
            self.assertIn(texto, ctx.exception.messages[0])
        with override_settings(MEDIA_MAX_UPLOAD_MB=0.00001), self.assertRaises(ValidationError) as ctx:
            self.registrar(e, cargo=archivo("grande.pdf", b"%PDF " + b"x" * 100))
        self.assertIn("máximo permitido", ctx.exception.messages[0])
        self.assertEqual((e.entregas.count(), e.adjuntos.filter(tipo="CARGO_RECEPCION").count()), (0, 0))

    def test_un_error_no_deja_nada_a_medias_ni_archivos_huerfanos(self):
        e = self.aprobado()
        antes_archivos, antes_historial = archivos_en_disco(), e.historial.count()
        with mock.patch.object(servicios, "mover", side_effect=ValidationError("falla al final")):
            with self.assertRaises(ValidationError):
                self.registrar(e)
        e.refresh_from_db()
        self.assertEqual(e.estado, E.LISTO_PARA_ENTREGA)
        self.assertEqual((e.entregas.count(), e.adjuntos.filter(tipo="CARGO_RECEPCION").count()), (0, 0))
        self.assertEqual(e.historial.count(), antes_historial)
        self.assertEqual(archivos_en_disco(), antes_archivos)
        self.assertFalse(Adjunto.objects.filter(bloqueado=True).exists())

    def test_solo_el_senior_del_entregable_el_gerente_y_el_admin_entregan(self):
        for usuario in (self.s1, self.gerente, self.admin):
            with self.subTest(usuario=usuario.username):
                self.assertEqual(self.registrar(self.aprobado(usuario.username), usuario).registrada_por, usuario)
        e = self.aprobado("Ajeno")
        for usuario in (self.j1, self.j2, self.s2):
            with self.subTest(usuario=usuario.username), self.assertRaises(PermissionDenied):
                self.registrar(e, usuario)
        e.refresh_from_db()
        self.assertEqual(e.estado, E.LISTO_PARA_ENTREGA)

    def test_solo_se_entrega_un_entregable_aprobado(self):
        for estado in (E.A_REALIZAR, E.EN_PROCESO, E.VERIFICACION_SENIOR, E.HECHO):
            with self.subTest(estado=estado):
                e = self.nuevo(self.c1, self.j1, self.s1, f"En {estado}", estado=estado)
                with self.assertRaises(ValidationError) as ctx:
                    self.registrar(e)
                self.assertIn("Solo se registra la entrega de un entregable «Aprobado»", ctx.exception.messages[0])

    def test_las_lecciones_se_siguen_generando_al_cerrar(self):
        from apps.conocimiento.models import LeccionAprendida

        e = self.aprobado()
        Observacion.objects.create(entregable=e, autor=self.s1, tipo_error="FORMATO", descripcion="Sin numeración",
                                   solucion="Se numeraron las páginas", resuelta=True)
        self.registrar(e)
        self.assertEqual(LeccionAprendida.objects.get().entregable_origen, e)

    def test_el_numero_es_unico_por_entregable_en_la_base(self):
        e, entrega = self.entregado()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Entrega.objects.create(entregable=e, numero=1, fecha_entrega=self.hoy, medio="CORREO", cargo=entrega.cargo,
                                   version_enviada=entrega.version_enviada, registrada_por=self.s1)

    def test_un_acta_recibida_u_observada_exige_archivo_tambien_en_la_base(self):
        e, entrega = self.entregado()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Entrega.objects.filter(pk=entrega.pk).update(acta_estado="RECIBIDA")


class EntregaDelCicloActualTests(EntregasBase):
    def test_la_entrega_registrada_se_consume_una_sola_vez(self):
        e, entrega = self.entregado()
        self.assertIsNotNone(entrega.cierre_id)
        self.assertIsNone(servicios.entrega_por_cerrar(e))

    def test_una_entrega_sin_cerrar_sirve_para_el_paso_y_queda_cerrada(self):
        e = self.aprobado()
        pendiente = Entrega.objects.create(
            entregable=e, numero=1, fecha_entrega=self.hoy, medio="OTRO", version_enviada=adjuntos.vigente(e, "VERSION_FINAL"),
            cargo=adjuntos.crear_adjunto(e, self.s1, archivo("cargo.pdf"), "CARGO_RECEPCION"), registrada_por=self.s1)
        servicios.mover(e, E.HECHO, self.s1)
        pendiente.refresh_from_db()
        self.assertEqual(pendiente.cierre.estado_nuevo, E.HECHO)
        self.assertTrue(pendiente.version_enviada.bloqueado)

    def test_tras_reabrir_no_sirve_la_entrega_anterior_y_la_siguiente_es_la_numero_2(self):
        e, primera = self.reabierto()
        self.assertEqual(e.estado, E.EN_PROCESO)
        # La corrección se sube como versión nueva; las bloqueadas siguen bloqueadas.
        nueva = adjuntos.subir(e, self.s1, archivo("final3.pdf", b"%PDF corregido"), "VERSION_FINAL", "Corrige el anexo")
        self.assertEqual(nueva.version, 3)
        self.assertTrue(Adjunto.objects.get(pk=primera.version_enviada_id).bloqueado)
        for o in e.observaciones.abiertas():
            obs_servicio.resolver(o, self.s1, "Se ajustó el anexo")
        servicios.mover(e, E.VERIFICACION_SENIOR, self.j1)
        servicios.mover(e, E.LISTO_PARA_ENTREGA, self.s1)
        with self.assertRaises(ValidationError) as ctx:
            servicios.mover(e, E.HECHO, self.s1)  # la entrega n.º 1 ya está cerrada: hace falta registrar otra
        self.assertIn("falta el cargo de recepción", ctx.exception.messages[0])
        segunda = self.registrar(e)
        self.assertEqual((segunda.numero, segunda.version_enviada.version, segunda.cargo.version), (2, 3, 2))
        primera.refresh_from_db()
        self.assertEqual((primera.numero, primera.acta_estado), (1, A.OBSERVADA))  # la primera no se sobrescribió
        self.assertTrue(Adjunto.objects.get(pk=segunda.version_enviada_id).bloqueado)
        self.assertEqual([x.numero for x in e.entregas.all()], [1, 2])


# ------------------------------------------------------------------ RF-29: interfaz de entrega


class FormularioDeEntregaTests(EntregasBase):
    def setUp(self):
        self.e = self.aprobado()
        self.url = reverse("entregable_entregar", args=[self.e.pk])

    def test_el_formulario_lo_ven_senior_gerente_y_admin_con_los_datos_del_wireframe(self):
        for usuario in (self.s1, self.gerente, self.admin):
            self.client.force_login(usuario)
            r = self.client.get(self.url)
            self.assertEqual(r.status_code, 200, usuario.username)
            for texto in ("Marcar como entregado", "Fecha de entrega", "Medio de entrega", "Cargo de recepción", "(obligatorio)",
                          "Versión enviada al cliente", "Mesa de partes", "FileDoc", "Versión final v2 (vigente)",
                          "Registrar entrega y marcar como «Entregado»"):
                self.assertContains(r, texto)

    def test_junior_403_y_ajenos_404(self):
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.datos_http(self.e)).status_code, 403)
        for usuario in (self.j2, self.s2):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get(self.url).status_code, 404)
            self.assertEqual(self.client.post(self.url, self.datos_http(self.e)).status_code, 404)
        self.e.refresh_from_db()
        self.assertEqual(self.e.estado, E.LISTO_PARA_ENTREGA)

    def test_sin_sesion_va_al_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_post_valido_entrega_y_lleva_a_la_seccion_de_entregas(self):
        self.client.force_login(self.s1)
        r = self.client.post(self.url, self.datos_http(self.e))
        self.assertRedirects(r, reverse("entregable_detalle", args=[self.e.pk]) + "#entregas", fetch_redirect_response=False)
        self.e.refresh_from_db()
        self.assertEqual(self.e.estado, E.HECHO)
        entrega = self.e.entregas.get()
        self.assertEqual((entrega.medio, entrega.acta_estado), ("MESA_DE_PARTES", A.PENDIENTE))
        r = self.client.get(reverse("entregable_detalle", args=[self.e.pk]))
        self.assertContains(r, "Entrega n.º 1 registrada")
        self.assertContains(r, "Pendiente · 0 días")

    def test_sin_cargo_se_explica_y_no_se_mueve(self):
        self.client.force_login(self.s1)
        datos = self.datos_http(self.e)
        del datos["cargo"]
        r = self.client.post(self.url, datos)
        self.assertContains(r, "Falta el cargo de recepción. Sin él no se puede marcar como entregado.")
        self.e.refresh_from_db()
        self.assertEqual((self.e.estado, self.e.entregas.count()), (E.LISTO_PARA_ENTREGA, 0))

    def test_errores_de_fecha_medio_y_version(self):
        self.client.force_login(self.s1)
        casos = [({"fecha_entrega": f"{self.hoy + datetime.timedelta(days=1):%Y-%m-%d}"}, "no puede ser futura"),
                 ({"fecha_entrega": ""}, "Falta la fecha de entrega"), ({"fecha_entrega": "31/02/2026"}, "no es una fecha válida"),
                 ({"medio": ""}, "Elija el medio de entrega"), ({"medio": "PALOMA"}, "Elija un medio de entrega válido"),
                 ({"version_enviada": ""}, "Elija la versión enviada"), ({"version_enviada": "99999"}, "mismo entregable"),
                 ({"comentario": "x" * 300}, "no puede superar los 255")]
        for cambios, texto in casos:
            with self.subTest(cambios=cambios):
                r = self.client.post(self.url, self.datos_http(self.e, **cambios))
                self.assertContains(r, texto)
        self.assertEqual(self.e.entregas.count(), 0)

    def test_una_version_de_otro_entregable_no_se_acepta_por_http(self):
        otro = self.aprobado("Otro")
        self.client.force_login(self.s1)
        r = self.client.post(self.url, self.datos_http(self.e, version_enviada=adjuntos.vigente(otro, "VERSION_FINAL").pk))
        self.assertContains(r, "mismo entregable")
        self.assertEqual(self.e.entregas.count(), 0)

    def test_requiere_csrf(self):
        estricto = Client(enforce_csrf_checks=True)
        estricto.force_login(self.s1)
        self.assertEqual(estricto.post(self.url, self.datos_http(self.e)).status_code, 403)
        self.assertEqual(self.e.entregas.count(), 0)

    def test_un_entregable_que_no_esta_aprobado_vuelve_al_detalle_con_el_motivo(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "En proceso", estado=E.EN_PROCESO)
        self.client.force_login(self.s1)
        r = self.client.get(reverse("entregable_entregar", args=[e.pk]), follow=True)
        self.assertRedirects(r, reverse("entregable_detalle", args=[e.pk]))
        self.assertContains(r, "Solo se registra la entrega de un entregable «Aprobado»")

    def test_el_formulario_avisa_si_no_hay_version_final(self):
        e = self.aprobado("Sin final", versiones=0)
        adjuntos.crear_adjunto(e, self.s1, archivo(), "BORRADOR", "borrador")
        self.client.force_login(self.s1)
        r = self.client.get(reverse("entregable_entregar", args=[e.pk]))
        self.assertContains(r, "no tiene una «Versión final»")
        r = self.client.post(reverse("entregable_entregar", args=[e.pk]), self.datos_http(e, version_enviada=""))
        self.assertContains(r, "Elija la versión enviada")

    def test_el_detalle_ofrece_marcar_como_entregado_solo_a_quien_puede(self):
        url = reverse("entregable_detalle", args=[self.e.pk])
        for usuario in (self.s1, self.gerente, self.admin):
            self.client.force_login(usuario)
            self.assertContains(self.client.get(url), f'href="{self.url}"')
        self.client.force_login(self.j1)
        self.assertNotContains(self.client.get(url), self.url)


class SoltarEnEntregadoTests(EntregasBase):
    """Tablero (HTMX): soltar una tarjeta de Aprobado en Entregado NO la mueve: abre el formulario de entrega."""

    def setUp(self):
        self.e = self.aprobado()

    def soltar(self, usuario, **datos):
        self.client.force_login(usuario)
        return self.client.post(reverse("entregable_estado", args=[self.e.pk]), {"estado": "HECHO", **datos}, **HX)

    def test_el_senior_es_llevado_al_formulario_y_el_entregable_no_se_mueve(self):
        for usuario in (self.s1, self.gerente, self.admin):
            r = self.soltar(usuario)
            self.assertEqual(r.status_code, 200, usuario.username)
            self.assertEqual(r["HX-Redirect"], reverse("entregable_entregar", args=[self.e.pk]))
            self.e.refresh_from_db()
            self.assertEqual(self.e.estado, E.LISTO_PARA_ENTREGA)
        self.assertFalse(self.e.historial.exclude(estado_anterior=F("estado_nuevo")).exists())  # ninguna transición

    def test_quien_no_puede_entregar_recibe_403_y_el_tablero_con_el_motivo(self):
        r = self.soltar(self.j1)
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("HX-Redirect", r)
        self.assertContains(r, "No tiene permiso", status_code=403)

    def test_un_senior_ajeno_no_ve_el_entregable(self):
        self.assertEqual(self.soltar(self.s2).status_code, 404)

    def test_el_formulario_clasico_del_detalle_tambien_abre_el_formulario(self):
        self.client.force_login(self.s1)
        r = self.client.post(reverse("entregable_estado", args=[self.e.pk]), {"estado": "HECHO"})
        self.assertRedirects(r, reverse("entregable_entregar", args=[self.e.pk]), fetch_redirect_response=False)
        self.e.refresh_from_db()
        self.assertEqual(self.e.estado, E.LISTO_PARA_ENTREGA)

    def test_otras_transiciones_a_entregado_siguen_siendo_invalidas(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "En proceso", estado=E.EN_PROCESO)
        self.client.force_login(self.s1)
        r = self.client.post(reverse("entregable_estado", args=[e.pk]), {"estado": "HECHO"}, **HX)
        self.assertEqual(r.status_code, 422)
        self.assertContains(r, "Ese movimiento no está permitido", status_code=422)

    def test_el_script_del_tablero_devuelve_la_tarjeta_y_deja_decidir_al_servidor(self):
        js = (Path(settings.BASE_DIR) / "static" / "js" / "tablero.js").read_text(encoding="utf-8")
        self.assertIn('"LISTO_PARA_ENTREGA" && evento.to.dataset.estado === "HECHO"', js)
        self.assertIn("insertBefore(evento.item, lugar)", js)

    def test_la_tarjeta_entregada_muestra_la_fecha_y_el_acta_en_texto(self):
        e, _ = self.entregado("Tarjeta")
        self.client.force_login(self.gerente)
        html = self.client.get(reverse("tablero")).content.decode()
        self.assertIn(f"Entregado {self.hoy:%d/%m/%Y} · ", html)
        self.assertIn("Acta pendiente", html)
        entregas.registrar_acta(e.entregas.get(), self.s1, A.OBSERVADA, archivo("acta.pdf"))
        self.assertIn("Acta observada", self.client.get(reverse("tablero")).content.decode())


# ------------------------------------------------------------------ RF-29: acta


class ActaTests(EntregasBase):
    def setUp(self):
        self.e, self.entrega = self.entregado()

    def post_acta(self, usuario, entrega=None, **datos):
        self.client.force_login(usuario)
        datos = {"estado": "RECIBIDA", "archivo": archivo("acta.pdf", b"%PDF acta"), **datos}
        return self.client.post(reverse("entrega_acta", args=[(entrega or self.entrega).pk]), datos, follow=True)

    def test_recibida_guarda_el_archivo_bloqueado_y_avisa_al_junior(self):
        r = self.post_acta(self.s1)
        self.assertContains(r, "Acta de la entrega n.º 1 registrada como recibida.")
        self.entrega.refresh_from_db()
        self.assertEqual(self.entrega.acta_estado, A.RECIBIDA)
        self.assertEqual((self.entrega.acta.tipo, self.entrega.acta.version, self.entrega.acta.bloqueado),
                         ("ACTA_CONFORMIDAD", 1, True))
        self.assertIsNotNone(self.entrega.acta_actualizada_en)
        n = Notificacion.objects.get(tipo="ACTA")  # quien registra (s1) no se avisa a sí mismo
        self.assertEqual(n.usuario, self.j1)
        self.assertIn(self.e.codigo, n.mensaje)
        self.assertIn("fue recibida", n.mensaje)
        self.assertEqual(n.destino, reverse("entregable_detalle", args=[self.e.pk]) + "#entregas")

    def test_observada_avisa_al_junior_y_al_senior_revisor_cuando_la_registra_otro(self):
        self.post_acta(self.gerente, estado="OBSERVADA")
        avisos = Notificacion.objects.filter(tipo="ACTA")
        self.assertEqual({n.usuario for n in avisos}, {self.j1, self.s1})
        self.assertTrue(all("quedó observada" in n.mensaje and self.e.codigo in n.mensaje for n in avisos))

    def test_el_archivo_y_el_estado_son_obligatorios(self):
        self.client.force_login(self.s1)
        url = reverse("entrega_acta", args=[self.entrega.pk])
        r = self.client.post(url, {"estado": "RECIBIDA"}, follow=True)
        self.assertContains(r, "Adjunte el archivo del acta")
        r = self.client.post(url, {"archivo": archivo()}, follow=True)
        self.assertContains(r, "Elija el estado del acta")
        r = self.client.post(url, {"estado": "PENDIENTE", "archivo": archivo()}, follow=True)
        self.assertContains(r, "Elija el estado del acta")
        r = self.client.post(url, {"estado": "RECIBIDA", "archivo": SimpleUploadedFile("acta.exe", b"x")}, follow=True)
        self.assertContains(r, "no es de un tipo permitido")
        self.entrega.refresh_from_db()
        self.assertEqual((self.entrega.acta_estado, self.entrega.acta), (A.PENDIENTE, None))
        self.assertFalse(Notificacion.objects.filter(tipo="ACTA").exists())
        self.assertFalse(self.e.adjuntos.filter(tipo="ACTA_CONFORMIDAD").exists())

    def test_permisos_junior_403_y_ajenos_404(self):
        self.assertEqual(self.post_acta(self.j1).status_code, 403)
        self.assertEqual(self.post_acta(self.j2).status_code, 404)
        self.assertEqual(self.post_acta(self.s2).status_code, 404)
        for usuario in (self.gerente, self.admin):
            self.assertEqual(self.post_acta(usuario).status_code, 200)
        with self.assertRaises(PermissionDenied):
            entregas.registrar_acta(self.entrega, self.j1, A.RECIBIDA, archivo())

    def test_solo_post_y_con_csrf(self):
        url = reverse("entrega_acta", args=[self.entrega.pk])
        self.client.force_login(self.s1)
        self.assertEqual(self.client.get(url).status_code, 405)
        estricto = Client(enforce_csrf_checks=True)
        estricto.force_login(self.s1)
        self.assertEqual(estricto.post(url, {"estado": "RECIBIDA", "archivo": archivo()}).status_code, 403)

    def test_actualizar_el_acta_crea_otra_version_sin_reescribir_la_anterior(self):
        entregas.registrar_acta(self.entrega, self.s1, A.OBSERVADA, archivo("acta1.pdf", b"%PDF uno"))
        primera = Entrega.objects.get(pk=self.entrega.pk).acta
        entregas.registrar_acta(self.entrega, self.s1, A.RECIBIDA, archivo("acta2.pdf", b"%PDF dos"))
        self.entrega.refresh_from_db()
        self.assertEqual((self.entrega.acta_estado, self.entrega.acta.version), (A.RECIBIDA, 2))
        self.assertEqual(Adjunto.objects.get(pk=primera.pk).nombre_original, "acta1.pdf")
        self.assertTrue(Adjunto.objects.get(pk=primera.pk).bloqueado)

    def test_el_acta_solo_se_registra_para_la_ultima_entrega_mientras_esta_entregado(self):
        e, primera = self.reabierto("Con reentrega")
        r = self.post_acta(self.s1, entrega=primera)
        self.assertContains(r, "El acta solo se registra para la última entrega, mientras el entregable está «Entregado»")
        primera.refresh_from_db()
        self.assertEqual(primera.acta_estado, A.OBSERVADA)

    def test_historial_y_seccion_del_detalle(self):
        self.post_acta(self.s1)
        self.client.force_login(self.s1)
        html = self.client.get(reverse("entregable_detalle", args=[self.e.pk])).content.decode()
        self.assertIn("Registró el acta de conformidad de la entrega n.º 1: Recibida (v1, acta.pdf)", html)
        self.assertIn("Entregas y acta de conformidad", html)
        self.assertIn(reverse("adjunto_descargar", args=[self.entrega.cargo_id]), html)

    def test_el_formulario_de_acta_lo_ven_senior_gerente_y_admin_pero_no_el_junior(self):
        url = reverse("entregable_detalle", args=[self.e.pk])
        for usuario in (self.s1, self.gerente, self.admin):
            self.client.force_login(usuario)
            self.assertContains(self.client.get(url), "Registrar acta de la entrega n.º 1")
        self.client.force_login(self.j1)
        r = self.client.get(url)
        self.assertNotContains(r, "Registrar acta de la entrega")
        self.assertContains(r, "Pendiente · 0 días")  # sí ve el estado


# ------------------------------------------------------------------ reapertura (caso 21b)


class ReaperturaTests(EntregasBase):
    def test_sin_acta_observada_salir_de_entregado_se_rechaza(self):
        casos = {"sin entregas (cerrado antes del Sprint 2)": self.nuevo(self.c1, self.j1, self.s1, "Antiguo", estado=E.HECHO)}
        e, _ = self.entregado("Pendiente")
        casos["acta pendiente"] = e
        e, _ = self.entregado("Recibida", acta=A.RECIBIDA)
        casos["acta recibida"] = e
        for nombre, e in casos.items():
            for usuario in (self.s1, self.gerente, self.admin):
                with self.subTest(caso=nombre, usuario=usuario.username), self.assertRaises(ValidationError) as ctx:
                    servicios.mover(e, E.EN_PROCESO, usuario, tipo_error="CONTENIDO", descripcion="x")
                self.assertIn("Solo se reabre un entregable «Entregado» cuando el acta de la última entrega está «Observada»",
                              ctx.exception.messages[0])
            e.refresh_from_db()
            self.assertEqual(e.estado, E.HECHO, nombre)
            self.assertFalse(e.observaciones.exists(), nombre)

    def test_las_demas_salidas_de_entregado_siguen_prohibidas(self):
        e, _ = self.entregado("Observada", acta=A.OBSERVADA)
        for destino in (E.A_REALIZAR, E.VERIFICACION_SENIOR, E.LISTO_PARA_ENTREGA):
            with self.subTest(destino=destino), self.assertRaises(ValidationError) as ctx:
                servicios.mover(e, destino, self.gerente)
            self.assertIn("no está permitido", ctx.exception.messages[0])

    def test_con_el_acta_observada_la_reabren_el_senior_el_gerente_y_el_admin_con_observacion(self):
        for usuario in (self.s1, self.gerente, self.admin):
            with self.subTest(usuario=usuario.username):
                e, entrega = self.entregado(f"Observada {usuario.username}", acta=A.OBSERVADA)
                servicios.mover(e, E.EN_PROCESO, usuario, tipo_error="CONTENIDO", descripcion="El cliente objetó el cuadro 3")
                e.refresh_from_db()
                self.assertEqual(e.estado, E.EN_PROCESO)
                obs = e.observaciones.get()
                self.assertEqual((obs.estado, obs.autor, obs.responsable, obs.tipo_error),
                                 ("PENDIENTE", usuario, self.j1, "CONTENIDO"))
                h = e.historial.order_by("-id").first()
                self.assertEqual(h.descripcion, "Estado: Entregado → En proceso (Reabierto por acta observada con observación (Contenido))")
                self.assertEqual(h.usuario, usuario)

    def test_exige_observacion_como_una_devolucion(self):
        e, _ = self.entregado("Observada", acta=A.OBSERVADA)
        for kwargs in ({}, {"tipo_error": "CONTENIDO"}, {"descripcion": "algo"}, {"tipo_error": "MALO", "descripcion": "x"},
                       {"tipo_error": "FORMATO", "descripcion": "   "}, {"observaciones": []}):
            with self.subTest(**kwargs), self.assertRaises(ValidationError) as ctx:
                servicios.mover(e, E.EN_PROCESO, self.s1, **kwargs)
            self.assertEqual(ctx.exception.code, "observacion_requerida")
        e.refresh_from_db()
        self.assertEqual((e.estado, e.observaciones.count()), (E.HECHO, 0))

    def test_varias_observaciones_a_la_vez(self):
        e, _ = self.entregado("Observada", acta=A.OBSERVADA)
        servicios.mover(e, E.EN_PROCESO, self.s1, observaciones=[
            {"tipo_error": "CONTENIDO", "descripcion": "Cuadro 3"}, {"tipo_error": "FORMATO", "descripcion": "Márgenes"}])
        self.assertEqual(e.observaciones.count(), 2)
        self.assertEqual(e.historial.order_by("-id").first().descripcion,
                         "Estado: Entregado → En proceso (Reabierto por acta observada con 2 observaciones (Contenido, Formato))")

    def test_el_junior_y_el_senior_ajeno_no_reabren(self):
        e, _ = self.entregado("Observada", acta=A.OBSERVADA)
        for usuario in (self.j1, self.j2, self.s2):
            with self.subTest(usuario=usuario.username), self.assertRaises(PermissionDenied):
                servicios.mover(e, E.EN_PROCESO, usuario, tipo_error="CONTENIDO", descripcion="x")
        e.refresh_from_db()
        self.assertEqual(e.estado, E.HECHO)

    def test_avisa_al_junior_con_el_codigo_y_queda_con_correcciones_pendientes(self):
        e, _ = self.reabierto()
        aviso = Notificacion.objects.filter(usuario=self.j1, tipo="OBSERVACION").latest("id")
        self.assertIn(e.codigo, aviso.mensaje)
        self.assertIn("se reabrió porque el acta de conformidad quedó observada", aviso.mensaje)
        self.assertEqual(aviso.destino, servicios.enlace_observaciones(e))
        self.client.force_login(self.j1)
        self.assertContains(self.client.get(reverse("entregable_detalle", args=[e.pk])), "Con correcciones pendientes")

    def test_las_versiones_bloqueadas_siguen_bloqueadas_y_la_correccion_es_version_nueva(self):
        e, entrega = self.reabierto()
        self.assertTrue(Adjunto.objects.get(pk=entrega.version_enviada_id).bloqueado)
        self.assertTrue(Adjunto.objects.get(pk=entrega.cargo_id).bloqueado)
        with self.assertRaises(PermissionDenied):
            adjuntos.eliminar(entrega.version_enviada, self.gerente)
        self.assertEqual(adjuntos.subir(e, self.j1, archivo("final3.pdf"), "VERSION_FINAL", "Corrección").version, 3)

    def test_reabrir_desde_el_detalle_con_el_formulario_clasico(self):
        e, entrega = self.entregado("Observada", acta=A.OBSERVADA)
        self.client.force_login(self.s1)
        html = self.client.get(reverse("entregable_detalle", args=[e.pk])).content.decode()
        self.assertIn("Reabrir para corrección", html)
        self.assertIn("la siguiente entrega será la n.º 2", html)
        url = reverse("entregable_estado", args=[e.pk])
        r = self.client.post(url, {"estado": "EN_PROCESO"}, follow=True)
        self.assertContains(r, "Para devolver el entregable debe indicar el tipo de error")
        e.refresh_from_db()
        self.assertEqual(e.estado, E.HECHO)
        r = self.client.post(url, {"estado": "EN_PROCESO", "tipo_error": "CONTENIDO", "descripcion": "Ajustar el anexo"}, follow=True)
        self.assertContains(r, "pasó a «En proceso»")
        e.refresh_from_db()
        self.assertEqual(e.estado, E.EN_PROCESO)

    def test_el_detalle_ofrece_reabrir_solo_con_el_acta_observada_y_a_quien_puede(self):
        observada, _ = self.entregado("Observada", acta=A.OBSERVADA)
        recibida, _ = self.entregado("Recibida", acta=A.RECIBIDA)
        pendiente, _ = self.entregado("Pendiente")
        for usuario in (self.s1, self.gerente, self.admin):
            self.client.force_login(usuario)
            self.assertContains(self.client.get(reverse("entregable_detalle", args=[observada.pk])), "Reabrir para corrección")
            for e in (recibida, pendiente):
                self.assertNotContains(self.client.get(reverse("entregable_detalle", args=[e.pk])), "Reabrir para corrección")
        self.client.force_login(self.j1)
        self.assertNotContains(self.client.get(reverse("entregable_detalle", args=[observada.pk])), "Reabrir para corrección")

    def test_desde_el_tablero_pide_la_observacion_y_luego_reabre(self):
        e, _ = self.entregado("Observada", acta=A.OBSERVADA)
        self.client.force_login(self.s1)
        url = reverse("entregable_estado", args=[e.pk])
        r = self.client.post(url, {"estado": "EN_PROCESO"}, **HX)
        self.assertEqual(r.status_code, 422)
        self.assertIn("pedirObservacion", r["HX-Trigger"])
        r = self.client.post(url, {"estado": "EN_PROCESO", "tipo_error": "FORMATO", "descripcion": "Reformatear"}, **HX)
        self.assertEqual(r.status_code, 200)
        e.refresh_from_db()
        self.assertEqual(e.estado, E.EN_PROCESO)

    def test_el_tablero_rechaza_reabrir_sin_acta_observada(self):
        e, _ = self.entregado("Recibida", acta=A.RECIBIDA)
        self.client.force_login(self.s1)
        r = self.client.post(reverse("entregable_estado", args=[e.pk]), {"estado": "EN_PROCESO"}, **HX)
        self.assertEqual(r.status_code, 422)
        self.assertContains(r, "Solo se reabre un entregable", status_code=422)
        self.assertNotIn("pedirObservacion", r.get("HX-Trigger", ""))


# ------------------------------------------------------------------ alerta de acta pendiente (caso 20)


class AlertaDeActaTests(EntregasBase):
    def entrega_hace(self, dias, titulo="Alerta"):
        e = self.aprobado(titulo)
        return e, self.registrar(e, fecha_entrega=self.hoy - datetime.timedelta(days=dias))

    def avisos(self):
        return Notificacion.objects.filter(tipo="ACTA")

    def test_pasado_el_plazo_avisa_al_junior_y_al_senior_una_sola_vez(self):
        e, entrega = self.entrega_hace(6)
        self.assertEqual(generar_alertas_acta(self.hoy), 2)
        self.assertEqual({n.usuario for n in self.avisos()}, {self.j1, self.s1})
        for _ in range(3):
            self.assertEqual(generar_alertas_acta(self.hoy), 0)
        self.assertEqual(generar_alertas_acta(self.hoy + datetime.timedelta(days=10)), 0)
        self.assertEqual(self.avisos().count(), 2)
        n = self.avisos().get(usuario=self.j1)
        self.assertEqual(n.entregable, e)
        self.assertEqual(n.mensaje, f"El acta de conformidad de la entrega n.º 1 de {e.referencia} sigue pendiente: 6 días "
                                    f"desde la entrega del {entrega.fecha_entrega:%d/%m/%Y}.")
        self.assertEqual(n.destino, reverse("entregable_detalle", args=[e.pk]) + "#entregas")
        entrega.refresh_from_db()
        self.assertIsNotNone(entrega.alerta_acta_en)

    def test_el_plazo_es_mas_de_acta_dias_pendiente_dias(self):
        self.entrega_hace(5)  # justo 5 días: todavía no
        self.assertEqual(generar_alertas_acta(self.hoy), 0)
        self.assertEqual(generar_alertas_acta(self.hoy + datetime.timedelta(days=1)), 2)  # al día siguiente son 6

    @override_settings(ACTA_DIAS_PENDIENTE=2)
    def test_el_plazo_es_configurable(self):
        self.entrega_hace(3)
        self.assertEqual(generar_alertas_acta(self.hoy), 2)

    def test_un_acta_ya_registrada_no_genera_aviso(self):
        e, entrega = self.entrega_hace(10)
        entregas.registrar_acta(entrega, self.s1, A.RECIBIDA, archivo("acta.pdf"))
        Notificacion.objects.all().delete()
        self.assertEqual(generar_alertas_acta(self.hoy), 0)

    def test_una_entrega_reciente_no_genera_aviso(self):
        self.entrega_hace(0)
        self.assertEqual(generar_alertas_acta(self.hoy), 0)
        self.assertFalse(self.avisos().exists())

    def test_cada_entrega_avisa_una_vez_y_solo_a_sus_responsables(self):
        self.entrega_hace(8, "Uno")
        e2 = self.aprobado("Dos", contrato=self.c2, junior=self.j2, senior=self.s2)
        self.registrar(e2, self.s2, fecha_entrega=self.hoy - datetime.timedelta(days=9))
        self.assertEqual(generar_alertas_acta(self.hoy), 4)
        self.assertEqual({n.usuario for n in self.avisos().filter(entregable=e2)}, {self.j2, self.s2})
        self.assertEqual(generar_alertas_acta(self.hoy), 0)

    def test_si_el_aviso_ya_se_reclamo_no_se_duplica_aunque_la_tarea_corra_a_la_vez(self):
        _, entrega = self.entrega_hace(7)
        Entrega.objects.filter(pk=entrega.pk).update(alerta_acta_en=entrega.registrada_en)  # otra ejecución la reclamó
        self.assertEqual(generar_alertas_acta(self.hoy), 0)
        self.assertFalse(self.avisos().exists())

    def test_la_tarea_programada_diaria_y_el_comando_la_incluyen(self):
        self.entrega_hace(6)
        self.assertEqual(programador.tarea_alertas(), 2)  # vencimientos: ninguno (plazo a 10 días y entregado); actas: 2
        self.assertEqual(programador.tarea_alertas(), 0)  # idempotente
        self.assertEqual(self.avisos().count(), 2)
        salida = StringIO()
        call_command("generar_alertas", stdout=salida)
        self.assertIn("Avisos de acta pendiente creados: 0", salida.getvalue())

    def test_el_comando_informa_los_avisos_de_acta_creados(self):
        self.entrega_hace(6)
        salida = StringIO()
        call_command("generar_alertas", stdout=salida)
        self.assertIn("Avisos de acta pendiente creados: 2", salida.getvalue())

    def test_el_tipo_acta_y_la_configuracion_existen(self):
        self.assertEqual(settings.ACTA_DIAS_PENDIENTE, 5)
        raiz = Path(settings.BASE_DIR)
        self.assertIn("ACTA_DIAS_PENDIENTE=5", (raiz / ".env.example").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ historial /entregas/


class HistorialDeEntregasTests(EntregasBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.cliente2 = Cliente.objects.create(nombre="Otro Cliente Ficticio", sector="TELECOM")
        cls.c3 = Contrato.objects.create(cliente=cls.cliente2, numero_contrato="C3", fecha_inicio=datetime.date(2026, 1, 1),
                                         fecha_fin=datetime.date(2027, 1, 1), senior_responsable=cls.s1)
        cls.c3.juniors.set([cls.j1])

    def setUp(self):
        self.url = reverse("entregas")
        self.e1_, self.n1 = self.entregado("De C1", acta=A.RECIBIDA)
        self.e2_ = self.aprobado("De C2", contrato=self.c2, junior=self.j2, senior=self.s2)
        self.n2 = self.registrar(self.e2_, self.s2, fecha_entrega=self.hoy - datetime.timedelta(days=40), medio="FILEDOC")
        self.e3_ = self.aprobado("De C3", contrato=self.c3)
        self.n3 = self.registrar(self.e3_, fecha_entrega=self.hoy - datetime.timedelta(days=10))

    def codigos(self, usuario, **params):
        self.client.force_login(usuario)
        r = self.client.get(self.url, params)
        self.assertEqual(r.status_code, 200)
        return {en.entregable.codigo for en in r.context["entregas"]}

    def test_cada_rol_ve_solo_las_entregas_de_sus_entregables(self):
        self.assertEqual(self.codigos(self.gerente), {self.e1_.codigo, self.e2_.codigo, self.e3_.codigo})
        self.assertEqual(self.codigos(self.admin), {self.e1_.codigo, self.e2_.codigo, self.e3_.codigo})
        self.assertEqual(self.codigos(self.s1), {self.e1_.codigo, self.e3_.codigo})
        self.assertEqual(self.codigos(self.s2), {self.e2_.codigo})
        self.assertEqual(self.codigos(self.j1), {self.e1_.codigo, self.e3_.codigo})
        self.assertEqual(self.codigos(self.j2), {self.e2_.codigo})

    def test_un_junior_sin_entregas_ve_la_lista_vacia(self):
        j3 = Usuario.objects.create_user("j3", password="x", rol="JUNIOR")
        self.client.force_login(j3)
        self.assertContains(self.client.get(self.url), "No hay entregas para mostrar")

    def test_sin_sesion_va_al_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_filtros_por_cliente_contrato_periodo_y_acta(self):
        todos = {self.e1_.codigo, self.e2_.codigo, self.e3_.codigo}
        self.assertEqual(self.codigos(self.gerente, cliente=self.cliente2.pk), {self.e3_.codigo})
        self.assertEqual(self.codigos(self.gerente, cliente=self.cliente.pk), {self.e1_.codigo, self.e2_.codigo})
        self.assertEqual(self.codigos(self.gerente, contrato=self.c2.pk), {self.e2_.codigo})
        self.assertEqual(self.codigos(self.gerente, acta="RECIBIDA"), {self.e1_.codigo})
        self.assertEqual(self.codigos(self.gerente, acta="PENDIENTE"), {self.e2_.codigo, self.e3_.codigo})
        self.assertEqual(self.codigos(self.gerente, acta="OBSERVADA"), set())
        desde = f"{self.hoy - datetime.timedelta(days=15):%Y-%m-%d}"
        self.assertEqual(self.codigos(self.gerente, desde=desde), {self.e1_.codigo, self.e3_.codigo})
        hasta = f"{self.hoy - datetime.timedelta(days=20):%Y-%m-%d}"
        self.assertEqual(self.codigos(self.gerente, hasta=hasta), {self.e2_.codigo})
        self.assertEqual(self.codigos(self.gerente, desde=f"{self.n3.fecha_entrega:%Y-%m-%d}",
                                      hasta=f"{self.n3.fecha_entrega:%Y-%m-%d}"), {self.e3_.codigo})  # inclusivo
        self.assertEqual(self.codigos(self.gerente, cliente=self.cliente.pk, acta="PENDIENTE"), {self.e2_.codigo})
        self.assertEqual(self.codigos(self.gerente, desde="basura", hasta="2026-13-45", acta="X", cliente="abc"), todos)

    def test_los_filtros_nunca_amplian_la_visibilidad(self):
        # El junior 2 pide el contrato y el cliente de otros: no obtiene nada que no vea.
        self.assertEqual(self.codigos(self.j2, contrato=self.c1.pk), set())
        self.assertEqual(self.codigos(self.j2, cliente=self.cliente2.pk), set())
        self.assertEqual(self.codigos(self.j2, contrato=self.c2.pk, acta="PENDIENTE"), {self.e2_.codigo})
        self.assertEqual(self.codigos(self.s2, cliente=self.cliente.pk), {self.e2_.codigo})
        self.assertEqual(self.codigos(self.j1, acta="PENDIENTE"), {self.e3_.codigo})
        for usuario in (self.j1, self.j2, self.s1, self.s2):
            visibles = set(entregables_visibles(usuario).values_list("codigo", flat=True))
            self.assertLessEqual(self.codigos(usuario), visibles)
            self.assertLessEqual(self.codigos(usuario, desde="2000-01-01", hasta="2100-01-01"), visibles)

    def test_los_desplegables_solo_ofrecen_lo_que_el_usuario_ve(self):
        self.client.force_login(self.j2)
        opciones = self.client.get(self.url).context["opciones"]
        self.assertEqual([c.nombre for c in opciones["clientes"]], [self.cliente.nombre])
        self.assertEqual([c.numero_contrato for c in opciones["contratos"]], ["C2"])
        self.client.force_login(self.gerente)
        self.assertEqual(len(self.client.get(self.url).context["opciones"]["contratos"]), 3)

    def test_las_columnas_y_las_descargas_por_vista_controlada(self):
        self.client.force_login(self.gerente)
        html = self.client.get(self.url).content.decode()
        for columna in ("Fecha", "Entregable", "Cliente · contrato", "N.º", "Medio", "Cargo", "Acta", "Registró"):
            self.assertIn(f"<th>{columna}</th>", html)
        self.assertIn(reverse("adjunto_descargar", args=[self.n1.cargo_id]), html)
        self.assertIn(reverse("adjunto_descargar", args=[self.n1.acta_id]), html)
        self.assertIn("Pendiente · 40 días", html)
        self.assertIn("Recibida", html)
        self.assertNotIn("/media/", html)

    def test_la_descarga_del_cargo_y_del_acta_respeta_la_visibilidad(self):
        for adjunto in (self.n1.cargo, self.n1.acta):
            url = reverse("adjunto_descargar", args=[adjunto.pk])
            self.client.force_login(self.j1)
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200)
            self.assertIn("attachment", r["Content-Disposition"])
            for ajeno in (self.j2, self.s2):
                self.client.force_login(ajeno)
                self.assertEqual(self.client.get(url).status_code, 404)
            self.client.logout()
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_es_una_pestana_de_entregables_y_htmx_recibe_el_fragmento(self):
        self.client.force_login(self.gerente)
        html = self.client.get(self.url).content.decode()
        self.assertIn('<a href="/entregas/" aria-current="true">Entregas</a>', html)
        self.assertEqual(html.count("<h1"), 1)
        self.assertEqual(re.findall(r'<nav aria-label="Principal">.*?aria-current="page">([^<]+)</a>', html, flags=re.S),
                         ["Entregables"])
        parcial = self.client.get(self.url, {"acta": "RECIBIDA"}, **HX).content.decode()
        self.assertNotIn("<html", parcial)
        self.assertIn(self.e1_.codigo, parcial)
        self.assertNotIn(self.e2_.codigo, parcial)
        self.assertIn("Estado del acta: Recibida", parcial)
        for nombre in ("entregables", "observaciones"):
            self.assertContains(self.client.get(reverse(nombre)), 'href="/entregas/"')

    def test_pagina_de_a_50(self):
        for n in range(52):
            e = self.aprobado(f"Masa {n}", versiones=1)
            self.registrar(e, fecha_entrega=self.hoy - datetime.timedelta(days=1))
        self.client.force_login(self.gerente)
        r = self.client.get(self.url)
        self.assertEqual(len(r.context["entregas"]), 50)
        self.assertEqual(r.context["total"], 55)
        self.assertContains(r, "Página 1 de 2")
        self.assertEqual(len(self.client.get(self.url, {"pagina": 2}).context["entregas"]), 5)

    def test_orden_de_la_mas_reciente_a_la_mas_antigua(self):
        self.client.force_login(self.gerente)
        fechas = [en.fecha_entrega for en in self.client.get(self.url).context["entregas"]]
        self.assertEqual(fechas, sorted(fechas, reverse=True))


# ------------------------------------------------------------------ varios


class DetalleDeEntregasTests(EntregasBase):
    def test_un_entregable_aprobado_dice_que_aun_no_se_entrego(self):
        e = self.aprobado()
        self.client.force_login(self.j1)
        r = self.client.get(reverse("entregable_detalle", args=[e.pk]))
        self.assertContains(r, "Este entregable aún no se entregó")
        self.assertNotContains(r, "Marcar como entregado")

    def test_el_detalle_lista_las_entregas_con_su_numero_y_cargo(self):
        e, primera = self.reabierto()
        for o in e.observaciones.abiertas():
            o.solucion, o.resuelta = "Corregido", True
            o.save()
        servicios.mover(e, E.VERIFICACION_SENIOR, self.j1)
        servicios.mover(e, E.LISTO_PARA_ENTREGA, self.s1)
        self.registrar(e)
        self.client.force_login(self.s1)
        html = self.client.get(reverse("entregable_detalle", args=[e.pk])).content.decode()
        self.assertEqual(html.count("<td>1</td><td>"), 1)
        self.assertIn("<td>2</td><td>", html)
        self.assertIn("Observada", html)
        seccion = html.split('id="entregas"')[1].split("<h2>Historial</h2>")[0]
        self.assertEqual(seccion.count('class="etiqueta bloqueada">Bloqueada'), 2)  # una por entrega: ambas versiones enviadas

    def test_la_navegacion_de_gerente_y_admin_no_gana_entradas(self):
        self.client.force_login(self.gerente)
        html = self.client.get(reverse("entregables")).content.decode()
        barra = re.search(r'<nav aria-label="Principal">(.*?)</nav>', html, flags=re.S).group(1)
        self.assertNotIn("/entregas/", barra)
