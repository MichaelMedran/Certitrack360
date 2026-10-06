"""Prueba de humo del panel técnico (SDD RF-18): ninguna pantalla debe romperse con los datos de demostración."""
import io
from unittest import mock

from django.contrib import admin
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.conocimiento import ollama
from apps.cuentas.models import Usuario
from apps.entregables.testing import MediaTemporal


def sin_ollama(ruta, cuerpo, timeout):
    raise ollama.OllamaNoDisponible("simulado")


class PanelTecnicoHumoTests(MediaTemporal, TestCase):
    @classmethod
    def setUpTestData(cls):
        with mock.patch.object(ollama, "_post", sin_ollama):
            call_command("seed_demo", stdout=io.StringIO())
        cls.admin = Usuario.objects.get(username="admin_demo")

    def test_todos_los_modelos_registrados_abren_su_listado_y_su_primera_ficha(self):
        self.client.force_login(self.admin)
        revisados = 0
        for modelo, config in admin.site._registry.items():
            etiqueta = modelo._meta.label
            with self.subTest(modelo=etiqueta):
                nombre = f"admin:{modelo._meta.app_label}_{modelo._meta.model_name}"
                self.assertEqual(self.client.get(reverse(f"{nombre}_changelist")).status_code, 200)
                primero = modelo.objects.first()
                if primero is not None:
                    r = self.client.get(reverse(f"{nombre}_change", args=[primero.pk]))
                    self.assertEqual(r.status_code, 200)
                revisados += 1
        self.assertGreaterEqual(revisados, 10)

    def test_cubre_las_tablas_principales(self):
        etiquetas = {m._meta.label for m in admin.site._registry}
        for esperado in ("cuentas.Usuario", "clientes.Cliente", "clientes.Contrato", "clientes.PlantillaTDR",
                         "entregables.Entregable", "entregables.Adjunto", "entregables.Observacion",
                         "entregables.HistorialEstado", "conocimiento.LeccionAprendida"):
            self.assertIn(esperado, etiquetas)

    def test_el_gerente_no_entra_a_ninguna_pantalla_del_panel(self):
        self.client.force_login(Usuario.objects.get(username="gerente_demo"))
        for modelo in admin.site._registry:
            nombre = f"admin:{modelo._meta.app_label}_{modelo._meta.model_name}_changelist"
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 302, modelo._meta.label)
