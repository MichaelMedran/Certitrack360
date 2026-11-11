"""Auditoría S3-H1 de HU-11 (tiempo por actividad, RF-32): un caso por criterio de Trello.

Cada prueba indica el criterio que cubre. Las pruebas del Sprint 2 (`test_tiempos.py`) ya cubren la lógica; aquí se
verifica lo que faltaba comprobar de punta a punta en pantalla (listado y ficha).
"""
import datetime

from django.urls import reverse
from django.utils import timezone

from apps.entregables import tiempos
from apps.entregables.models import RegistroTiempo
from apps.entregables.tests import Base

Etapa = RegistroTiempo.Etapa


class AuditoriaHU11Tests(Base):
    def setUp(self):
        super().setUp()
        self.ahora = timezone.now().replace(second=0, microsecond=0)

    def _ficha(self, usuario, entregable):
        self.client.force_login(usuario)
        return self.client.get(reverse("entregable_detalle", args=[entregable.pk]))

    def test_criterio_1_ficha_ofrece_iniciar_pausar_y_finalizar_cada_etapa(self):
        """Criterio 1: iniciar, pausar y finalizar por etapa desde la ficha."""
        r = self._ficha(self.j1, self.e1)
        self.assertContains(r, 'id="tiempo"')
        for valor, etiqueta in Etapa.choices:
            self.assertContains(r, f'<option value="{valor}"')
            self.assertContains(r, etiqueta)
        for accion in ("iniciar", "finalizar", "manual"):
            self.assertContains(r, f'value="{accion}"')
        # Con un tramo abierto, aparece también la acción de pausar.
        tiempos.iniciar(self.e1, self.j1, Etapa.RECOPILACION, ahora=self.ahora)
        r = self._ficha(self.j1, self.e1)
        self.assertContains(r, 'value="pausar"')
        # Recorre las tres etapas por la vista: iniciar -> pausar -> finalizar.
        url = reverse("entregable_tiempo", args=[self.e1.pk])
        tiempos.pausar(self.e1, self.j1, ahora=self.ahora + datetime.timedelta(minutes=5))
        for etapa in Etapa.values:
            self.assertEqual(self.client.post(url, {"accion": "iniciar", "etapa": etapa}).status_code, 302)
            self.assertEqual(self.client.post(url, {"accion": "pausar"}).status_code, 302)
            self.assertEqual(self.client.post(url, {"accion": "finalizar", "etapa": etapa}).status_code, 302)
            self.assertTrue(RegistroTiempo.objects.filter(entregable=self.e1, etapa=etapa, cierra_etapa=True).exists())

    def test_criterio_2_el_registro_guarda_y_el_listado_muestra_todos_los_datos(self):
        """Criterio 2: entregable, cliente, etapa, responsable, fecha, hora de inicio y de fin."""
        ini = self.ahora - datetime.timedelta(hours=3)
        fin = self.ahora - datetime.timedelta(hours=2)
        reg, _ = tiempos.iniciar(self.e1, self.j1, Etapa.CONSOLIDACION, ahora=ini)
        tiempos.pausar(self.e1, self.j1, ahora=fin)
        reg.refresh_from_db()
        self.assertEqual((reg.entregable, reg.usuario, reg.etapa, reg.inicio, reg.fin),
                         (self.e1, self.j1, Etapa.CONSOLIDACION, ini, fin))
        self.assertEqual(reg.entregable.contrato.cliente, self.cliente)

        self.client.force_login(self.j1)
        html = self.client.get(reverse("tiempos")).content.decode()
        for encabezado in ("Fecha", "Entregable", "Cliente", "Etapa", "Responsable", "Inicio", "Fin", "Duración"):
            self.assertIn(f"<th>{encabezado}</th>", html.replace('<th class="num">', "<th>"))
        local_ini, local_fin = timezone.localtime(ini), timezone.localtime(fin)
        for texto in (self.e1.codigo or self.e1.titulo, self.cliente.nombre, "Consolidación", self.j1.nombre,
                      local_ini.strftime("%d/%m/%Y"), local_ini.strftime("%H:%M"), local_fin.strftime("%H:%M")):
            self.assertIn(texto, html)

    def test_criterio_3_ajuste_manual_con_motivo_queda_marcado(self):
        """Criterio 3: ingreso manual con motivo, marcado como ajuste manual (en ficha y en listado)."""
        tiempos.registrar_manual(self.e1, self.j1, Etapa.REVISION, self.ahora - datetime.timedelta(hours=2),
                                 self.ahora - datetime.timedelta(hours=1), "Sin conexión", ahora=self.ahora)
        reg = RegistroTiempo.objects.get(entregable=self.e1)
        self.assertTrue(reg.manual)
        self.assertEqual(reg.motivo, "Sin conexión")
        self.assertContains(self._ficha(self.j1, self.e1), "Manual · «Sin conexión»")
        self.assertContains(self.client.get(reverse("tiempos")), "Manual · «Sin conexión»")

    def test_criterio_4_ficha_muestra_acumulado_por_etapa_y_total(self):
        """Criterio 4: acumulado por etapa y total del entregable en la ficha."""
        base = self.ahora
        tiempos.registrar_manual(self.e1, self.j1, Etapa.RECOPILACION, base - datetime.timedelta(hours=5),
                                 base - datetime.timedelta(hours=4), "a", ahora=base)
        tiempos.registrar_manual(self.e1, self.j1, Etapa.RECOPILACION, base - datetime.timedelta(hours=3),
                                 base - datetime.timedelta(hours=2, minutes=30), "b", ahora=base)
        tiempos.registrar_manual(self.e1, self.j1, Etapa.REVISION, base - datetime.timedelta(hours=2),
                                 base - datetime.timedelta(hours=1), "c", ahora=base)
        resumen = tiempos.resumen_tiempos(self.e1, self.j1, ahora=base)
        por_codigo = {e["codigo"]: e["duracion_texto"] for e in resumen["etapas"]}
        self.assertEqual(por_codigo, {Etapa.RECOPILACION: "1 h 30 min", Etapa.CONSOLIDACION: "0 h 00 min",
                                      Etapa.REVISION: "1 h 00 min"})
        self.assertEqual(resumen["total_texto"], "2 h 30 min")
        r = self._ficha(self.j1, self.e1)
        self.assertContains(r, "Total del entregable")
        self.assertContains(r, "1 h 30 min")
        self.assertContains(r, "2 h 30 min")

    def test_criterio_5_visibilidad_y_filtros_en_pantalla(self):
        """Criterio 5: junior sus registros, senior los de sus entregables, gerente todos; filtros por cliente,
        etapa, responsable y fechas (en la pantalla `/tiempos/`)."""
        otro_cliente = self.e2.contrato.cliente  # mismo cliente en la base; se crea uno distinto para filtrar
        from apps.clientes.models import Cliente
        otro_cliente = Cliente.objects.create(nombre="Cliente Otro", sector="TELECOM")
        self.c2.cliente = otro_cliente
        self.c2.save()
        base = self.ahora
        tiempos.registrar_manual(self.e1, self.j1, Etapa.RECOPILACION, base - datetime.timedelta(hours=4),
                                 base - datetime.timedelta(hours=3), "motivo-j1", ahora=base)
        tiempos.registrar_manual(self.e1, self.s1, Etapa.REVISION, base - datetime.timedelta(hours=2),
                                 base - datetime.timedelta(hours=1), "motivo-s1", ahora=base)
        tiempos.registrar_manual(self.e2, self.j2, Etapa.CONSOLIDACION, base - datetime.timedelta(hours=6),
                                 base - datetime.timedelta(hours=5), "motivo-j2", ahora=base)
        url = reverse("tiempos")

        self.client.force_login(self.j1)
        html = self.client.get(url).content.decode()
        self.assertIn("motivo-j1", html)
        self.assertNotIn("motivo-s1", html)
        self.assertNotIn("motivo-j2", html)

        self.client.force_login(self.s1)
        html = self.client.get(url).content.decode()
        self.assertIn("motivo-j1", html)
        self.assertIn("motivo-s1", html)
        self.assertNotIn("motivo-j2", html)

        self.client.force_login(self.gerente)
        html = self.client.get(url).content.decode()
        for m in ("motivo-j1", "motivo-s1", "motivo-j2"):
            self.assertIn(m, html)

        def motivos(**params):
            h = self.client.get(url, params).content.decode()
            return {m for m in ("motivo-j1", "motivo-s1", "motivo-j2") if m in h}

        self.assertEqual(motivos(cliente=otro_cliente.pk), {"motivo-j2"})
        self.assertEqual(motivos(etapa=Etapa.REVISION), {"motivo-s1"})
        self.assertEqual(motivos(responsable=self.j1.pk), {"motivo-j1"})
        hoy = timezone.localdate(base)
        self.assertEqual(motivos(desde=(hoy + datetime.timedelta(days=1)).isoformat()), set())
        self.assertEqual(motivos(hasta=(hoy - datetime.timedelta(days=30)).isoformat()), set())
        self.assertEqual(motivos(desde=(hoy - datetime.timedelta(days=1)).isoformat(),
                                 hasta=(hoy + datetime.timedelta(days=1)).isoformat(), etapa=Etapa.CONSOLIDACION),
                         {"motivo-j2"})
        # Los cuatro filtros y las fechas existen en la pantalla.
        html = self.client.get(url).content.decode()
        for nombre in ("cliente", "etapa", "responsable", "desde", "hasta"):
            self.assertIn(f'name="{nombre}"', html)
