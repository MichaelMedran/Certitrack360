"""Pruebas del calendario (SDD RF-12; caso 2 de la sección 17.2)."""
import re
from pathlib import Path

from django.conf import settings
from django.templatetags.static import static
from django.test import override_settings
from django.urls import reverse

from apps.entregables.models import Entregable
from apps.entregables.test_filtros import FiltrosBase

E = Entregable.Estado


class CalendarioTests(FiltrosBase):
    def eventos(self, usuario, **params):
        self.client.force_login(usuario)
        r = self.client.get(reverse("calendario_eventos"), params)
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_la_ruta_es_la_del_sdd(self):
        self.assertEqual(reverse("calendario_eventos"), "/api/calendario/eventos/")

    def test_cada_rol_ve_solo_sus_plazos(self):
        titulos = lambda usuario: {ev["title"].split(": ", 1)[1].split(" — ")[0] for ev in self.eventos(usuario)}
        self.assertEqual(titulos(self.j1), {"E1", "a-vencido", "b-hoy", "c-critico", "g-hecho"})
        self.assertEqual(titulos(self.j2), {"E2", "d-proximo", "f-proximo", "h-vencido"})
        self.assertEqual(titulos(self.s2), {"E2", "f-proximo", "h-vencido"})
        self.assertEqual(len(self.eventos(self.gerente)), 9)

    def test_un_junior_no_obtiene_eventos_ajenos_aunque_pida_otro_rango(self):
        ids = {ev["id"] for ev in self.eventos(self.j1, start="2000-01-01", end="2100-01-01")}
        self.assertEqual(ids, {e.pk for e in Entregable.objects.filter(junior_asignado=self.j1)})

    def test_la_urgencia_va_en_texto_ademas_del_color(self):
        por_titulo = {ev["title"]: ev for ev in self.eventos(self.gerente)}
        vencido = next(ev for t, ev in por_titulo.items() if "a-vencido" in t)
        self.assertTrue(vencido["title"].endswith("— Vencido"))
        self.assertEqual(vencido["extendedProps"], {"estado": "EN_PROCESO", "urgencia": "VENCIDO"})
        critico = next(ev for t, ev in por_titulo.items() if "c-critico" in t)
        self.assertTrue(critico["title"].endswith("— Crítico"))
        proximo = next(ev for t, ev in por_titulo.items() if "d-proximo" in t)
        self.assertTrue(proximo["title"].endswith("— Próximo"))
        self.assertEqual(len({vencido["color"], critico["color"], proximo["color"]}), 3)

    def test_lo_normal_y_lo_hecho_no_llevan_etiqueta_de_urgencia(self):
        por_titulo = {ev["title"]: ev for ev in self.eventos(self.gerente)}
        for clave in ("E1", "g-hecho"):
            titulo = next(t for t in por_titulo if t.endswith(clave))
            self.assertNotIn("—", titulo)

    def test_el_estado_va_en_el_titulo(self):
        titulos = [ev["title"] for ev in self.eventos(self.gerente)]
        self.assertTrue(any(t.startswith("[Verificación senior]") for t in titulos))
        self.assertTrue(any(t.startswith("[Hecho]") for t in titulos))

    @override_settings(ALERT_THRESHOLDS_DAYS=[1, 0])
    def test_la_urgencia_del_calendario_usa_los_umbrales_de_las_alertas(self):
        proximos = [ev for ev in self.eventos(self.gerente) if "c-critico" in ev["title"]]
        self.assertEqual(proximos[0]["extendedProps"]["urgencia"], "NORMAL")  # vence en 2 días y el umbral es 1

    def test_los_eventos_enlazan_al_detalle(self):
        ev = self.eventos(self.j1)[0]
        self.assertEqual(ev["url"], reverse("entregable_detalle", args=[ev["id"]]))

    def test_filtra_por_rango_de_fechas(self):
        todos = self.eventos(self.gerente)
        acotados = self.eventos(self.gerente, start=self.hoy.isoformat(), end=self.hoy.isoformat())
        self.assertEqual({ev["id"] for ev in acotados}, {self.b.pk})
        self.assertGreater(len(todos), len(acotados))

    def test_la_pagina_requiere_sesion(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("calendario")).status_code, 302)
        self.assertEqual(self.client.get(reverse("calendario_eventos")).status_code, 302)


class PaginaDelCalendarioTests(FiltrosBase):
    def ver(self):
        self.client.force_login(self.gerente)
        return self.client.get(reverse("calendario"))

    def test_carga_las_bibliotecas_locales_y_pide_los_eventos_a_la_api(self):
        r = self.ver()
        self.assertContains(r, f'src="{static("js/fullcalendar.min.js")}"')
        self.assertContains(r, f'src="{static("js/fullcalendar-es.min.js")}"')
        self.assertContains(r, '<div id="calendario"></div>')
        self.assertContains(r, f'events: "{reverse("calendario_eventos")}"')

    def test_en_pantallas_angostas_parte_de_la_lista_y_vuelve_a_la_cuadricula_al_ensanchar(self):
        html = self.ver().content.decode()
        self.assertIn("window.matchMedia('(max-width: 700px)')", html)
        self.assertIn("initialView: angosto.matches ? 'listMonth' : 'dayGridMonth'", html)
        self.assertIn("calendario.changeView(angosto.matches ? 'listMonth' : 'dayGridMonth')", html)

    def test_los_titulos_largos_se_ajustan_para_que_la_urgencia_se_lea_en_el_mes(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "certitrack.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"#calendario \.fc-daygrid-event\s*\{\s*white-space:\s*normal")
        self.assertRegex(css, r"#calendario \.fc-header-toolbar\s*\{\s*flex-wrap:\s*wrap")
