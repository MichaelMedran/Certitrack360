import io
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import TestCase

from apps.cuentas.management.commands import esperar_bd


class EsperarBdTests(TestCase):
    def ejecutar(self, *args):
        salida = io.StringIO()
        call_command("esperar_bd", *args, stdout=salida)
        return salida.getvalue()

    def test_con_la_base_lista_termina_enseguida(self):
        self.assertIn("Base de datos lista", self.ejecutar())

    def test_con_migraciones_aplicadas_tambien_termina(self):
        self.assertIn("Base de datos lista", self.ejecutar("--migrado"))

    def test_reintenta_hasta_que_la_base_responde(self):
        with mock.patch.object(esperar_bd.connection, "ensure_connection",
                               side_effect=[OperationalError("conexión rechazada"), None]), \
                mock.patch.object(esperar_bd.time, "sleep") as dormir:
            texto = self.ejecutar()
        self.assertIn("la base de datos no responde (conexión rechazada)", texto)
        self.assertIn("Base de datos lista", texto)
        dormir.assert_called_once_with(1)

    def test_espera_a_que_se_apliquen_las_migraciones(self):
        with mock.patch.object(esperar_bd, "migraciones_pendientes", side_effect=[True, False]), \
                mock.patch.object(esperar_bd.time, "sleep"):
            texto = self.ejecutar("--migrado")
        self.assertIn("hay migraciones pendientes", texto)
        self.assertIn("Base de datos lista", texto)

    def test_se_rinde_despues_de_los_intentos(self):
        with mock.patch.object(esperar_bd.connection, "ensure_connection", side_effect=OperationalError("caída")), \
                mock.patch.object(esperar_bd.time, "sleep"):
            with self.assertRaises(CommandError):
                self.ejecutar("--intentos", "3")
