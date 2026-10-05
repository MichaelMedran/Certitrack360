"""Pruebas de adjuntos (SDD RF-11, casos 6, 7 y 8 de la sección 17.2)."""
import os

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from apps.alertas.models import Notificacion
from apps.clientes.models import PlantillaTDR
from apps.entregables import adjuntos, servicios
from apps.entregables.models import Adjunto, Entregable, HistorialEstado
from apps.entregables.tests import Base

E = Entregable.Estado
PDF = b"%PDF-1.4\n% archivo ficticio de prueba\n"


def pdf(nombre="informe.pdf", contenido=PDF):
    return SimpleUploadedFile(nombre, contenido, content_type="application/pdf")


class VersionadoTests(Base):
    def test_cada_subida_del_mismo_tipo_es_una_version_nueva(self):
        a1 = adjuntos.subir(self.e1, self.j1, pdf(contenido=b"%PDF primera"), "BORRADOR")
        a2 = adjuntos.subir(self.e1, self.j1, pdf(contenido=b"%PDF segunda"), "BORRADOR", "corregido")
        self.assertEqual((a1.version, a2.version), (1, 2))
        self.assertNotEqual(a1.archivo.name, a2.archivo.name)
        with a1.archivo.open("rb") as f:  # la versión 1 sigue intacta
            self.assertEqual(f.read(), b"%PDF primera")
        self.assertEqual(a2.comentario, "corregido")

    def test_la_version_es_por_entregable_y_por_tipo(self):
        adjuntos.subir(self.e1, self.j1, pdf(), "BORRADOR")
        otro_tipo = adjuntos.subir(self.e1, self.j1, pdf(), "EVIDENCIA")
        otro_entregable = adjuntos.subir(self.e2, self.j2, pdf(), "BORRADOR")
        self.assertEqual(otro_tipo.version, 1)
        self.assertEqual(otro_entregable.version, 1)

    def test_ruta_ordenada_por_cliente_contrato_y_entregable(self):
        a = adjuntos.subir(self.e1, self.j1, pdf(), "TDR")
        partes = a.archivo.name.split("/")
        self.assertEqual(len(partes), 4)
        self.assertTrue(partes[0].startswith(f"{self.cliente.pk}-"))
        self.assertTrue(partes[1].startswith(f"{self.c1.pk}-"))
        self.assertEqual(partes[2], f"entregable-{self.e1.pk}")
        self.assertTrue(partes[3].startswith("tdr_v1_"))

    def test_tipo_invalido(self):
        with self.assertRaises(ValidationError):
            adjuntos.subir(self.e1, self.j1, pdf(), "VIRUS")
        self.assertEqual(Adjunto.objects.count(), 0)


class ValidacionDeArchivosTests(Base):
    def test_extensiones_no_permitidas(self):
        for nombre in ("programa.exe", "script.php", "doc.pdf.exe", "sin_extension", ".pdf", "pagina.html", "datos.csv"):
            with self.subTest(nombre=nombre), self.assertRaises(ValidationError) as ctx:
                adjuntos.subir(self.e1, self.j1, SimpleUploadedFile(nombre, b"x"), "OTRO")
            self.assertIn("tipo permitido", ctx.exception.messages[0])
        self.assertEqual(Adjunto.objects.count(), 0)

    def test_extensiones_permitidas_sin_importar_mayusculas(self):
        for nombre in ("a.pdf", "b.DOCX", "c.xlsx", "d.pptx", "e.png", "f.JPG", "g.txt"):
            with self.subTest(nombre=nombre):
                self.assertTrue(adjuntos.subir(self.e1, self.j1, SimpleUploadedFile(nombre, b"x"), "OTRO"))

    @override_settings(MEDIA_MAX_UPLOAD_MB=0.001)  # ~1 KB
    def test_tamano_excedido(self):
        with self.assertRaises(ValidationError) as ctx:
            adjuntos.subir(self.e1, self.j1, pdf(contenido=b"x" * 2000), "BORRADOR")
        self.assertIn("máximo permitido", ctx.exception.messages[0])
        self.assertEqual(Adjunto.objects.count(), 0)
        self.assertTrue(adjuntos.subir(self.e1, self.j1, pdf(contenido=b"x" * 500), "BORRADOR"))

    @override_settings(ALLOWED_UPLOAD_EXTENSIONS=["pdf"])
    def test_extensiones_configurables(self):
        with self.assertRaises(ValidationError):
            adjuntos.subir(self.e1, self.j1, SimpleUploadedFile("a.txt", b"x"), "OTRO")
        self.assertTrue(adjuntos.subir(self.e1, self.j1, pdf(), "OTRO"))

    def test_archivo_vacio(self):
        with self.assertRaises(ValidationError):
            adjuntos.subir(self.e1, self.j1, pdf(contenido=b""), "BORRADOR")

    def test_nombre_saneado(self):
        casos = {
            "../../etc/passwd.pdf": "passwd.pdf",
            "C:\\Users\\x\\informe.pdf": "informe.pdf",
            "informe técnico (v2).pdf": "informe_técnico_v2.pdf",
            "a\x00b\x1f.pdf": "ab.pdf",
            ".htaccess.txt": "htaccess.txt",
            "..": "archivo",
        }
        for crudo, esperado in casos.items():
            with self.subTest(crudo=crudo):
                self.assertEqual(adjuntos.sanear_nombre(crudo), esperado)

    def test_nombre_largo_se_acorta_y_conserva_la_extension(self):
        nombre = adjuntos.sanear_nombre("x" * 400 + ".pdf")
        self.assertLessEqual(len(nombre), adjuntos.NOMBRE_MAX)
        self.assertTrue(nombre.endswith(".pdf"))

    def test_el_archivo_queda_dentro_de_media_root(self):
        a = adjuntos.subir(self.e1, self.j1, SimpleUploadedFile("../../fuera.pdf", PDF), "BORRADOR")
        ruta = os.path.realpath(a.archivo.path)
        raiz = os.path.realpath(settings.MEDIA_ROOT)
        self.assertEqual(os.path.commonpath([ruta, raiz]), raiz)
        self.assertTrue(os.path.exists(ruta))


class PermisosDeSubidaTests(Base):
    def test_junior_asignado_solo_en_estados_iniciales(self):
        permitido = {E.A_REALIZAR: True, E.EN_PROCESO: True, E.VERIFICACION_SENIOR: False,
                     E.LISTO_PARA_ENTREGA: False, E.HECHO: False}
        for estado, esperado in permitido.items():
            with self.subTest(estado=estado):
                e = self.nuevo(self.c1, self.j1, self.s1, f"E-{estado}", estado=estado)
                self.assertEqual(adjuntos.puede_subir(self.j1, e), esperado)

    def test_junior_ajeno_no_sube(self):
        self.assertFalse(adjuntos.puede_subir(self.j2, self.e1))

    def test_senior_responsable_sube_en_cualquier_estado_pero_no_el_ajeno(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "V", estado=E.VERIFICACION_SENIOR)
        self.assertTrue(adjuntos.puede_subir(self.s1, e))
        self.assertFalse(adjuntos.puede_subir(self.s2, e))

    def test_gerente_y_admin_suben_siempre(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "H", estado=E.HECHO)
        self.assertTrue(adjuntos.puede_subir(self.gerente, e))
        self.assertTrue(adjuntos.puede_subir(self.admin, e))

    def test_subir_sin_permiso_lanza_error(self):
        with self.assertRaises(PermissionDenied):
            adjuntos.subir(self.e1, self.j2, pdf(), "BORRADOR")

    def test_http_subida_correcta_y_rechazos(self):
        url = reverse("adjunto_subir", args=[self.e1.pk])
        self.client.force_login(self.j1)
        r = self.client.post(url, {"tipo": "BORRADOR", "archivo": pdf(), "comentario": "primera"})
        self.assertRedirects(r, reverse("entregable_detalle", args=[self.e1.pk]))
        self.assertEqual(self.e1.adjuntos.count(), 1)

        self.client.force_login(self.j2)  # junior de otro contrato: ni siquiera ve el entregable
        self.assertEqual(self.client.post(url, {"tipo": "BORRADOR", "archivo": pdf()}).status_code, 404)
        self.client.force_login(self.s2)
        self.assertEqual(self.client.post(url, {"tipo": "BORRADOR", "archivo": pdf()}).status_code, 404)
        self.assertEqual(self.e1.adjuntos.count(), 1)

    def test_http_junior_no_sube_cuando_ya_esta_en_verificacion(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "V", estado=E.VERIFICACION_SENIOR)
        self.client.force_login(self.j1)
        r = self.client.post(reverse("adjunto_subir", args=[e.pk]), {"tipo": "BORRADOR", "archivo": pdf()})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(e.adjuntos.count(), 0)

    def test_http_mensajes_claros_al_fallar_la_validacion(self):
        self.client.force_login(self.j1)
        url = reverse("adjunto_subir", args=[self.e1.pk])
        r = self.client.post(url, {"tipo": "BORRADOR", "archivo": SimpleUploadedFile("a.exe", b"x")}, follow=True)
        self.assertContains(r, "no es de un tipo permitido")
        r = self.client.post(url, {"tipo": "BORRADOR"}, follow=True)
        self.assertContains(r, "Elija el archivo que desea subir.")
        r = self.client.post(url, {"archivo": pdf()}, follow=True)
        self.assertContains(r, "Elija el tipo de adjunto.")
        self.assertEqual(self.e1.adjuntos.count(), 0)

    def test_http_requiere_sesion_y_metodo_post(self):
        url = reverse("adjunto_subir", args=[self.e1.pk])
        self.assertEqual(self.client.post(url, {"tipo": "BORRADOR", "archivo": pdf()}).status_code, 302)
        self.client.force_login(self.j1)
        self.assertEqual(self.client.get(url).status_code, 405)


class DescargaTests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.adjunto = adjuntos.subir(cls.e1, cls.j1, pdf("acta técnica.pdf", b"%PDF contenido secreto"), "EVIDENCIA")

    def descargar(self, usuario):
        if usuario:
            self.client.force_login(usuario)
        return self.client.get(reverse("adjunto_descargar", args=[self.adjunto.pk]))

    def test_con_acceso_se_descarga_como_adjunto(self):
        for usuario in (self.j1, self.s1, self.gerente, self.admin):
            with self.subTest(usuario=usuario.username):
                r = self.descargar(usuario)
                self.assertEqual(r.status_code, 200)
                self.assertEqual(b"".join(r.streaming_content), b"%PDF contenido secreto")
                self.assertIn("attachment", r["Content-Disposition"])
                self.assertIn("no-store", r["Cache-Control"])
                r.close()

    def test_sin_acceso_se_deniega(self):
        for usuario in (self.j2, self.s2):
            with self.subTest(usuario=usuario.username):
                self.assertEqual(self.descargar(usuario).status_code, 404)

    def test_sin_sesion_redirige_al_login(self):
        r = self.client.get(reverse("adjunto_descargar", args=[self.adjunto.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("login"), r["Location"])

    def test_el_acceso_sigue_la_visibilidad_si_cambia_el_responsable(self):
        self.e1.junior_asignado = self.j2
        self.e1.save()
        self.assertEqual(self.descargar(self.j1).status_code, 404)  # ya no es suyo
        r = self.descargar(self.j2)
        self.assertEqual(r.status_code, 200)
        r.close()

    def test_no_hay_url_publica_para_los_archivos(self):
        with self.assertRaises(ValueError):
            self.adjunto.archivo.url
        self.assertIsNone(settings.MEDIA_URL)
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get("/media/" + self.adjunto.archivo.name).status_code, 404)
        self.assertEqual(self.client.get("/" + self.adjunto.archivo.name).status_code, 404)

    def test_archivo_faltante_en_disco_da_404(self):
        a = adjuntos.subir(self.e1, self.j1, pdf("otro.pdf"), "OTRO")
        os.remove(a.archivo.path)
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(reverse("adjunto_descargar", args=[a.pk])).status_code, 404)


class EliminacionTests(Base):
    def setUp(self):
        self.adjunto = adjuntos.subir(self.e1, self.j1, pdf("borrar.pdf"), "BORRADOR")

    def eliminar(self, usuario):
        self.client.force_login(usuario)
        return self.client.post(reverse("adjunto_eliminar", args=[self.adjunto.pk]))

    def test_junior_y_senior_no_eliminan(self):
        for usuario in (self.j1, self.s1):
            with self.subTest(usuario=usuario.username):
                self.assertEqual(self.eliminar(usuario).status_code, 403)
        self.assertTrue(Adjunto.objects.filter(pk=self.adjunto.pk).exists())
        self.assertTrue(os.path.exists(self.adjunto.archivo.path))

    def test_usuario_sin_acceso_recibe_404(self):
        self.assertEqual(self.eliminar(self.s2).status_code, 404)

    def test_gerente_y_admin_eliminan_y_se_borra_el_archivo(self):
        for usuario in (self.gerente, self.admin):
            with self.subTest(usuario=usuario.username):
                a = adjuntos.subir(self.e1, self.j1, pdf("x.pdf"), "OTRO")
                ruta = a.archivo.path
                self.client.force_login(usuario)
                with self.captureOnCommitCallbacks(execute=True):
                    r = self.client.post(reverse("adjunto_eliminar", args=[a.pk]))
                self.assertEqual(r.status_code, 302)
                self.assertFalse(Adjunto.objects.filter(pk=a.pk).exists())
                self.assertFalse(os.path.exists(ruta))

    def test_eliminar_requiere_post(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(reverse("adjunto_eliminar", args=[self.adjunto.pk])).status_code, 405)

    def test_borrar_el_entregable_borra_sus_archivos(self):
        ruta = self.adjunto.archivo.path
        with self.captureOnCommitCallbacks(execute=True):
            Entregable.objects.get(pk=self.e1.pk).delete()
        self.assertFalse(os.path.exists(ruta))


class HistorialDeAdjuntosTests(Base):
    def test_subida_y_eliminacion_quedan_en_el_historial(self):
        a = adjuntos.subir(self.e1, self.j1, pdf("informe_enero.pdf"), "BORRADOR")
        adjuntos.eliminar(a, self.gerente)
        subida, eliminacion = self.e1.historial.order_by("id")
        self.assertEqual(subida.usuario, self.j1)
        self.assertEqual(subida.detalle, "Subió adjunto: Borrador v1 (informe_enero.pdf)")
        self.assertEqual(eliminacion.usuario, self.gerente)
        self.assertEqual(eliminacion.detalle, "Eliminó adjunto: Borrador v1 (informe_enero.pdf)")
        for fila in (subida, eliminacion):
            self.assertFalse(fila.es_cambio_de_estado)
            self.assertEqual(fila.estado_anterior, E.A_REALIZAR)
            self.assertEqual(fila.descripcion, fila.detalle)

    def test_un_cambio_de_estado_sigue_mostrando_el_estado(self):
        servicios.mover(self.e1, E.EN_PROCESO, self.j1)
        h = self.e1.historial.get()
        self.assertTrue(h.es_cambio_de_estado)
        self.assertEqual(h.descripcion, "Estado: A realizar → En proceso")

    def test_el_detalle_muestra_el_historial_de_adjuntos(self):
        adjuntos.subir(self.e1, self.j1, pdf("informe_enero.pdf"), "BORRADOR")
        self.client.force_login(self.j1)
        r = self.client.get(reverse("entregable_detalle", args=[self.e1.pk]))
        self.assertContains(r, "Subió adjunto: Borrador v1 (informe_enero.pdf)")


class AdjuntosRequeridosTests(Base):
    """Poka-Yoke: sin los adjuntos que exige la plantilla no se pasa a Verificación senior."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.exigente = PlantillaTDR.objects.create(
            nombre="Con adjuntos", campos_requeridos=[], adjuntos_requeridos=["BORRADOR", "EVIDENCIA"]
        )

    def entregable_en_proceso(self):
        e = self.nuevo(self.c1, self.j1, self.s1, "Exigente", estado=E.EN_PROCESO)
        e.plantilla = self.exigente
        e.save()
        return e

    def test_faltan_todos_y_el_mensaje_los_nombra(self):
        e = self.entregable_en_proceso()
        with self.assertRaises(ValidationError) as ctx:
            servicios.mover(e, E.VERIFICACION_SENIOR, self.j1)
        mensaje = ctx.exception.messages[0]
        self.assertIn("«Borrador»", mensaje)
        self.assertIn("«Evidencia»", mensaje)
        e.refresh_from_db()
        self.assertEqual(e.estado, E.EN_PROCESO)

    def test_el_mensaje_solo_nombra_lo_que_falta(self):
        e = self.entregable_en_proceso()
        adjuntos.subir(e, self.j1, pdf(), "BORRADOR")
        with self.assertRaises(ValidationError) as ctx:
            servicios.mover(e, E.VERIFICACION_SENIOR, self.j1)
        self.assertIn("«Evidencia»", ctx.exception.messages[0])
        self.assertNotIn("«Borrador»", ctx.exception.messages[0])

    def test_con_todos_los_adjuntos_pasa_a_verificacion(self):
        e = self.entregable_en_proceso()
        adjuntos.subir(e, self.j1, pdf(), "BORRADOR")
        adjuntos.subir(e, self.j1, pdf("foto.png"), "EVIDENCIA")
        servicios.mover(e, E.VERIFICACION_SENIOR, self.j1)
        self.assertEqual(e.estado, E.VERIFICACION_SENIOR)

    def test_cualquier_version_cuenta_y_otros_tipos_no(self):
        e = self.entregable_en_proceso()
        adjuntos.subir(e, self.j1, pdf(), "TDR")
        adjuntos.subir(e, self.j1, pdf(), "OTRO")
        self.assertEqual(adjuntos.faltantes_requeridos(e), ["BORRADOR", "EVIDENCIA"])

    def test_plantilla_sin_requisitos_no_bloquea(self):
        servicios.mover(self.e1, E.EN_PROCESO, self.j1)
        servicios.mover(self.e1, E.VERIFICACION_SENIOR, self.j1)
        self.assertEqual(self.e1.estado, E.VERIFICACION_SENIOR)

    def test_la_regla_aplica_a_todos_los_roles_y_al_tablero(self):
        e = self.entregable_en_proceso()
        with self.assertRaises(ValidationError):
            servicios.mover(e, E.VERIFICACION_SENIOR, self.gerente)
        self.client.force_login(self.j1)
        r = self.client.post(reverse("tablero_mover", args=[e.pk]), {"estado": "VERIFICACION_SENIOR"},
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("«Borrador»", r.json()["error"])

    def test_no_se_pide_observacion_en_el_error_de_adjuntos(self):
        e = self.entregable_en_proceso()
        self.client.force_login(self.j1)
        r = self.client.post(reverse("tablero_mover", args=[e.pk]), {"estado": "VERIFICACION_SENIOR"},
                             content_type="application/json")
        self.assertFalse(r.json()["pide_observacion"])

    def test_plantilla_con_codigo_desconocido_no_rompe(self):
        self.exigente.adjuntos_requeridos = ["BORRADOR", "DESCONOCIDO"]
        self.exigente.save()
        e = self.entregable_en_proceso()
        with self.assertRaises(ValidationError) as ctx:
            servicios.mover(e, E.VERIFICACION_SENIOR, self.j1)
        self.assertIn("«DESCONOCIDO»", ctx.exception.messages[0])


class AvisoDeVerificacionTests(Base):
    def test_el_senior_recibe_aviso_cuando_el_entregable_llega_a_verificacion(self):
        servicios.mover(self.e1, E.EN_PROCESO, self.j1)
        servicios.mover(self.e1, E.VERIFICACION_SENIOR, self.j1)
        n = Notificacion.objects.get(tipo=Notificacion.Tipo.VERIFICACION)
        self.assertEqual((n.usuario, n.entregable), (self.s1, self.e1))

    def test_no_se_avisa_a_si_mismo(self):
        servicios.mover(self.e1, E.EN_PROCESO, self.s1)
        servicios.mover(self.e1, E.VERIFICACION_SENIOR, self.s1)
        self.assertFalse(Notificacion.objects.filter(tipo=Notificacion.Tipo.VERIFICACION).exists())


class PlantillaConAdjuntosTests(Base):
    def datos(self, **extra):
        d = {"nombre": "Nueva", "cliente": "", "formato": "PDF", "plazo_dias_por_defecto": 5,
             "campos_texto": "Periodo | texto", "adjuntos_requeridos": ["BORRADOR", "TDR"]}
        d.update(extra)
        return d

    def test_el_gerente_define_los_adjuntos_requeridos(self):
        self.client.force_login(self.gerente)
        r = self.client.post(reverse("adm_nuevo", args=["plantillas"]), self.datos())
        self.assertEqual(r.status_code, 302)
        p = PlantillaTDR.objects.get(nombre="Nueva")
        self.assertEqual(sorted(p.adjuntos_requeridos), ["BORRADOR", "TDR"])
        self.assertEqual(sorted(p.adjuntos_requeridos_etiquetas), ["Borrador", "TDR"])

    def test_se_pueden_dejar_vacios(self):
        self.client.force_login(self.gerente)
        self.client.post(reverse("adm_nuevo", args=["plantillas"]), self.datos(adjuntos_requeridos=[]))
        self.assertEqual(PlantillaTDR.objects.get(nombre="Nueva").adjuntos_requeridos, [])

    def test_tipo_invalido_se_rechaza(self):
        self.client.force_login(self.gerente)
        r = self.client.post(reverse("adm_nuevo", args=["plantillas"]), self.datos(adjuntos_requeridos=["MALO"]))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(PlantillaTDR.objects.filter(nombre="Nueva").exists())

    def test_la_edicion_conserva_la_seleccion(self):
        self.plantilla.adjuntos_requeridos = ["EVIDENCIA"]
        self.plantilla.save()
        self.client.force_login(self.gerente)
        r = self.client.get(reverse("adm_editar", args=["plantillas", self.plantilla.pk]))
        self.assertEqual(r.context["form"]["adjuntos_requeridos"].value(), ["EVIDENCIA"])

    def test_el_junior_no_accede(self):
        self.client.force_login(self.j1)
        self.assertEqual(self.client.post(reverse("adm_nuevo", args=["plantillas"]), self.datos()).status_code, 403)


class PanelTecnicoTests(Base):
    def test_el_panel_lista_y_abre_los_adjuntos_sin_romperse_aunque_no_tengan_url_publica(self):
        a = adjuntos.subir(self.e1, self.j1, pdf("informe_enero.pdf"), "BORRADOR")
        self.client.force_login(self.admin)
        r = self.client.get("/admin/entregables/adjunto/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "informe_enero.pdf")
        r = self.client.get(f"/admin/entregables/adjunto/{a.pk}/change/")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "/media/")
        self.assertContains(r, "Ubicación en el servidor")
        self.assertContains(r, a.archivo.name)  # la ubicación va en texto, sin enlace
        self.assertNotContains(r, f'href="{a.archivo.name}"')
        self.assertEqual(self.client.get("/admin/entregables/adjunto/add/").status_code, 403)  # se suben desde el entregable

    def test_los_demas_roles_no_entran_al_panel_de_adjuntos(self):
        for usuario in (self.j1, self.s1, self.gerente):
            self.client.force_login(usuario)
            self.assertEqual(self.client.get("/admin/entregables/adjunto/").status_code, 302)


class ServicioDirectoTests(Base):
    def test_crear_adjunto_con_contentfile_para_datos_de_demostracion(self):
        a = adjuntos.crear_adjunto(self.e1, self.s1, ContentFile(b"hola", name="nota.txt"), "OTRO", "demo")
        self.assertEqual((a.nombre_original, a.version, a.subido_por), ("nota.txt", 1, self.s1))
        self.assertTrue(os.path.exists(a.archivo.path))
