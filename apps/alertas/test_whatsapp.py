"""Canal de WhatsApp: cola de envíos, reintentos, filtro por tipo, celular del colaborador y conector de Meta."""
import datetime
import io
import json
import urllib.error
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.alertas import whatsapp
from apps.alertas.models import EnvioWhatsApp, Notificacion
from apps.alertas.programador import crear_programador
from apps.cuentas.models import Usuario

ENVIADOS = []


class ConectorPrueba:
    def enviar(self, numero, texto):
        ENVIADOS.append((numero, texto))
        return "wamid.prueba"


class ConectorRoto:
    def enviar(self, numero, texto):
        raise whatsapp.ErrorEnvio("sin red")


ACTIVO = {"WHATSAPP_CONECTOR": "apps.alertas.test_whatsapp.ConectorPrueba", "WHATSAPP_TIPOS": [], "SITIO_URL": ""}
ROTO = {**ACTIVO, "WHATSAPP_CONECTOR": "apps.alertas.test_whatsapp.ConectorRoto", "WHATSAPP_MAX_INTENTOS": 2}


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.con_celular = Usuario.objects.create_user("ana", password="x", rol="JUNIOR", celular="51987654321")
        cls.sin_celular = Usuario.objects.create_user("beto", password="x", rol="JUNIOR")
        cls.gerente = Usuario.objects.create_user("gema", password="x", rol="GERENTE")

    def setUp(self):
        ENVIADOS.clear()

    def aviso(self, usuario=None, tipo=Notificacion.Tipo.FICHA, mensaje="Una ficha espera confirmación.", enlace=""):
        return Notificacion.objects.create(usuario=usuario or self.con_celular, tipo=tipo, mensaje=mensaje, enlace=enlace)


class CanalApagadoTests(Base):
    def test_sin_configurar_no_encola_ni_envia(self):
        self.aviso()
        self.assertFalse(whatsapp.activo())
        self.assertEqual(whatsapp.despachar(), (0, 0))
        self.assertEqual(EnvioWhatsApp.objects.count(), 0)

    def test_sin_configurar_el_programador_no_tiene_la_tarea(self):
        self.assertIsNone(crear_programador().get_job("whatsapp"))

    @override_settings(**ACTIVO)
    def test_configurado_el_programador_despacha_cada_minuto(self):
        self.assertIsNotNone(crear_programador().get_job("whatsapp"))


@override_settings(**ACTIVO)
class ColaTests(Base):
    def test_envia_una_sola_vez_a_quien_tiene_celular(self):
        self.aviso()
        self.aviso(usuario=self.sin_celular)
        self.assertEqual(whatsapp.despachar(), (1, 0))
        self.assertEqual(whatsapp.despachar(), (0, 0))  # idempotente
        self.assertEqual(ENVIADOS, [("51987654321", "Una ficha espera confirmación.")])
        envio = EnvioWhatsApp.objects.get()
        self.assertEqual(envio.estado, EnvioWhatsApp.Estado.ENVIADO)
        self.assertEqual((envio.intentos, envio.id_externo), (1, "wamid.prueba"))
        self.assertIsNotNone(envio.enviado_en)

    def test_no_reenvia_el_historial_al_activar_el_canal(self):
        viejo = self.aviso()
        Notificacion.objects.filter(pk=viejo.pk).update(creada_en=timezone.now() - datetime.timedelta(hours=30))
        self.assertEqual(whatsapp.despachar(), (0, 0))
        self.assertEqual(ENVIADOS, [])

    def test_no_envia_a_un_usuario_inactivo(self):
        Usuario.objects.filter(pk=self.con_celular.pk).update(is_active=False)
        self.aviso()
        self.assertEqual(whatsapp.despachar(), (0, 0))

    @override_settings(WHATSAPP_TIPOS=["URGENTE"])
    def test_el_filtro_por_tipo_limita_lo_que_sale(self):
        self.aviso(tipo=Notificacion.Tipo.FICHA)
        self.aviso(tipo=Notificacion.Tipo.URGENTE, mensaje="URGENTE: atender hoy.")
        self.assertEqual(whatsapp.despachar(), (1, 0))
        self.assertEqual(ENVIADOS, [("51987654321", "URGENTE: atender hoy.")])

    @override_settings(SITIO_URL="http://certitrack.local:8000")
    def test_el_mensaje_lleva_la_direccion_del_aviso_si_se_configuro(self):
        self.aviso(enlace="/fichas/3/")
        whatsapp.despachar()
        self.assertEqual(ENVIADOS[0][1], "Una ficha espera confirmación. http://certitrack.local:8000/fichas/3/")

    def test_los_avisos_creados_en_bloque_tambien_salen(self):
        Notificacion.objects.bulk_create([
            Notificacion(usuario=self.con_celular, tipo=Notificacion.Tipo.REPORTE, mensaje="Reporte listo.", enlace="/reportes/"),
        ])
        self.assertEqual(whatsapp.despachar(), (1, 0))

    def test_despacha_al_confirmar_la_transaccion(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.aviso(tipo=Notificacion.Tipo.URGENTE, mensaje="URGENTE")
            whatsapp.despachar_al_confirmar()
            self.assertEqual(ENVIADOS, [])
        self.assertEqual(len(ENVIADOS), 1)


@override_settings(**ROTO)
class ReintentosTests(Base):
    def test_un_fallo_se_reintenta_y_al_agotarse_queda_fallido(self):
        self.aviso()
        self.assertEqual(whatsapp.despachar(), (0, 1))
        envio = EnvioWhatsApp.objects.get()
        self.assertEqual((envio.estado, envio.intentos, envio.error), (EnvioWhatsApp.Estado.PENDIENTE, 1, "sin red"))
        self.assertEqual(whatsapp.despachar(), (0, 1))
        envio.refresh_from_db()
        self.assertEqual((envio.estado, envio.intentos), (EnvioWhatsApp.Estado.FALLIDO, 2))
        self.assertEqual(whatsapp.despachar(), (0, 0))  # ya no se insiste

    def test_tras_un_fallo_el_siguiente_intento_puede_salir(self):
        self.aviso()
        whatsapp.despachar()
        with override_settings(WHATSAPP_CONECTOR=ACTIVO["WHATSAPP_CONECTOR"]):
            self.assertEqual(whatsapp.despachar(), (1, 0))
        envio = EnvioWhatsApp.objects.get()
        self.assertEqual((envio.estado, envio.intentos, envio.error), (EnvioWhatsApp.Estado.ENVIADO, 2, ""))

    @override_settings(WHATSAPP_CONECTOR="no.existe.Conector")
    def test_un_conector_mal_escrito_no_rompe_el_programador(self):
        self.aviso()
        self.assertEqual(whatsapp.despachar(), (0, 0))
        self.assertEqual(EnvioWhatsApp.objects.get().estado, EnvioWhatsApp.Estado.PENDIENTE)


class CelularTests(Base):
    def test_normaliza_los_formatos_habituales(self):
        casos = {
            "": "", "  ": "", "987654321": "51987654321", "987 654 321": "51987654321", "+51 987-654-321": "51987654321",
            "51987654321": "51987654321", "0051 987654321": "51987654321", "+1 (415) 555-2671": "14155552671",
        }
        for entrada, esperado in casos.items():
            with self.subTest(entrada=entrada):
                self.assertEqual(whatsapp.normalizar_celular(entrada), esperado)

    def test_rechaza_lo_que_no_es_un_celular(self):
        for entrada in ("abc", "12345", "9876543210123456789", "987654321 ext 2"):
            with self.subTest(entrada=entrada), self.assertRaises(ValidationError):
                whatsapp.normalizar_celular(entrada)

    def test_el_gerente_registra_el_celular_en_personal(self):
        self.client.force_login(self.gerente)
        datos = {"accion": "puesto", "usuario": self.sin_celular.pk, "puesto": "Asistente", "celular": "999 888 777"}
        self.client.post(reverse("personal"), datos)
        self.sin_celular.refresh_from_db()
        self.assertEqual((self.sin_celular.puesto, self.sin_celular.celular), ("Asistente", "51999888777"))
        html = self.client.get(reverse("personal") + f"?colaborador={self.sin_celular.pk}").content.decode()
        self.assertIn('value="51999888777"', html)
        self.assertIn("aún no está configurado", html)

    def test_un_celular_invalido_no_se_guarda_y_se_explica(self):
        self.client.force_login(self.gerente)
        datos = {"accion": "puesto", "usuario": self.con_celular.pk, "puesto": "", "celular": "123"}
        r = self.client.post(reverse("personal"), datos, follow=True)
        self.con_celular.refresh_from_db()
        self.assertEqual(self.con_celular.celular, "51987654321")
        self.assertContains(r, "entre 10 y 15 dígitos")

    def test_el_junior_no_puede_cambiar_celulares(self):
        self.client.force_login(self.sin_celular)
        datos = {"accion": "puesto", "usuario": self.con_celular.pk, "puesto": "", "celular": ""}
        self.assertEqual(self.client.post(reverse("personal"), datos).status_code, 403)


META = {"WHATSAPP_TOKEN": "secreto", "WHATSAPP_PHONE_ID": "1055", "WHATSAPP_PLANTILLA": "aviso_certitrack",
        "WHATSAPP_PLANTILLA_IDIOMA": "es", "WHATSAPP_API_URL": "https://graph.example/v1"}


@override_settings(**META)
class ConectorMetaTests(TestCase):
    def test_arma_la_peticion_con_la_plantilla_y_el_aviso(self):
        respuesta = mock.MagicMock()
        respuesta.__enter__.return_value.read.return_value = b'{"messages": [{"id": "wamid.1"}]}'
        with mock.patch("urllib.request.urlopen", return_value=respuesta) as abrir:
            self.assertEqual(whatsapp.ConectorMeta().enviar("51987654321", "CT-2026-00001 vence hoy."), "wamid.1")
        peticion = abrir.call_args.args[0]
        self.assertEqual(peticion.full_url, "https://graph.example/v1/1055/messages")
        self.assertEqual(peticion.get_header("Authorization"), "Bearer secreto")
        cuerpo = json.loads(peticion.data)
        self.assertEqual((cuerpo["messaging_product"], cuerpo["to"], cuerpo["type"]), ("whatsapp", "51987654321", "template"))
        self.assertEqual(cuerpo["template"]["name"], "aviso_certitrack")
        self.assertEqual(cuerpo["template"]["language"], {"code": "es"})
        self.assertEqual(cuerpo["template"]["components"][0]["parameters"], [{"type": "text", "text": "CT-2026-00001 vence hoy."}])

    def test_un_rechazo_del_proveedor_se_informa_sin_el_token(self):
        error = urllib.error.HTTPError("u", 401, "no", {}, io.BytesIO(b'{"error": {"message": "token vencido"}}'))
        with mock.patch("urllib.request.urlopen", side_effect=error), self.assertRaises(whatsapp.ErrorEnvio) as ctx:
            whatsapp.ConectorMeta().enviar("51987654321", "x")
        self.assertIn("401", str(ctx.exception))
        self.assertIn("token vencido", str(ctx.exception))
        self.assertNotIn("secreto", str(ctx.exception))

    def test_sin_red_es_un_error_de_envio(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("sin ruta")):
            with self.assertRaises(whatsapp.ErrorEnvio):
                whatsapp.ConectorMeta().enviar("51987654321", "x")

    @override_settings(WHATSAPP_TOKEN="")
    def test_sin_credenciales_no_intenta_conectarse(self):
        with mock.patch("urllib.request.urlopen") as abrir, self.assertRaises(whatsapp.ErrorEnvio) as ctx:
            whatsapp.ConectorMeta().enviar("51987654321", "x")
        abrir.assert_not_called()
        self.assertIn("WHATSAPP_TOKEN", str(ctx.exception))
