"""Pruebas de registro de tiempo por etapa, ajuste manual e historial filtrable (SDD Sprint 2, RF-32, §6.2, §7.7, §8, §13 caso 23)."""
import datetime
import re

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.entregables import filtros_tiempos, personal, tiempos
from apps.entregables.models import RegistroTiempo, ResponsableApoyo
from apps.entregables.tests import Base

Etapa = RegistroTiempo.Etapa


class ModeloRegistroTiempoTests(Base):
    """Restricciones de base de datos en RegistroTiempo (§6.2, caso 23)."""

    def test_un_usuario_no_puede_tener_dos_registros_abiertos_en_base_de_datos(self):
        ahora = timezone.now()
        RegistroTiempo.objects.create(
            entregable=self.e1,
            usuario=self.j1,
            etapa=Etapa.RECOPILACION,
            inicio=ahora - datetime.timedelta(minutes=30),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RegistroTiempo.objects.create(
                    entregable=self.e1,
                    usuario=self.j1,
                    etapa=Etapa.CONSOLIDACION,
                    inicio=ahora,
                )
        # Otro usuario sí puede tener su propio registro abierto al mismo tiempo.
        abierto_s1 = RegistroTiempo.objects.create(
            entregable=self.e1,
            usuario=self.s1,
            etapa=Etapa.REVISION,
            inicio=ahora,
        )
        self.assertTrue(abierto_s1.abierto)

    def test_registro_manual_exige_motivo_en_base_de_datos(self):
        ahora = timezone.now()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RegistroTiempo.objects.create(
                    entregable=self.e1,
                    usuario=self.j1,
                    etapa=Etapa.RECOPILACION,
                    inicio=ahora - datetime.timedelta(hours=2),
                    fin=ahora - datetime.timedelta(hours=1),
                    manual=True,
                    motivo="",
                )


class Caso23CronometroYManualTests(Base):
    """Caso 23 (§13, RF-32): cronómetro pausa el abierto anterior; ajuste manual exige motivo y valida límites."""

    def test_iniciar_pausa_el_registro_abierto_anterior_en_la_misma_transaccion(self):
        t0 = timezone.now() - datetime.timedelta(hours=2)
        t1 = t0 + datetime.timedelta(minutes=45)
        t2 = t1 + datetime.timedelta(minutes=30)

        r1, pausado_1 = tiempos.iniciar(self.e1, self.j1, Etapa.RECOPILACION, ahora=t0)
        self.assertIsNone(pausado_1)
        self.assertIsNone(r1.fin)

        # Iniciar otro tramo en otra etapa (o en otro entregable) cierra r1 en t1 y abre r2.
        r2, pausado_2 = tiempos.iniciar(self.e1, self.j1, Etapa.CONSOLIDACION, ahora=t1)
        self.assertEqual(pausado_2.pk, r1.pk)
        r1.refresh_from_db()
        self.assertEqual(r1.fin, t1)
        self.assertEqual(r1.duracion_texto, "0 h 45 min")
        self.assertIsNone(r2.fin)
        self.assertEqual(RegistroTiempo.objects.filter(usuario=self.j1, fin__isnull=True).count(), 1)

        # Pausar cierra r2 en t2.
        cerrado = tiempos.pausar(self.e1, self.j1, ahora=t2)
        self.assertEqual(cerrado.pk, r2.pk)
        self.assertEqual(cerrado.fin, t2)
        self.assertEqual(cerrado.duracion_texto, "0 h 30 min")
        self.assertEqual(RegistroTiempo.objects.filter(usuario=self.j1, fin__isnull=True).count(), 0)

        # Pausar cuando ya no hay registro abierto rechaza con ValidationError.
        with self.assertRaises(ValidationError):
            tiempos.pausar(self.e1, self.j1, ahora=t2)

    def test_finalizar_etapa_y_resumen_de_tiempos_por_etapa(self):
        t0 = timezone.now() - datetime.timedelta(hours=4)
        r1, _ = tiempos.iniciar(self.e1, self.j1, Etapa.RECOPILACION, ahora=t0)
        # Finalizar con el cronómetro corriendo cierra el tramo y marca cierra_etapa=True.
        t1 = t0 + datetime.timedelta(hours=2, minutes=15)
        tiempos.finalizar_etapa(self.e1, self.j1, Etapa.RECOPILACION, ahora=t1)
        r1.refresh_from_db()
        self.assertTrue(r1.cierra_etapa)
        self.assertEqual(r1.fin, t1)

        # Tramo en Consolidación aún en curso (pausado sin finalizar etapa).
        t2 = t1 + datetime.timedelta(minutes=10)
        t3 = t2 + datetime.timedelta(hours=1, minutes=20)
        tiempos.iniciar(self.e1, self.j1, Etapa.CONSOLIDACION, ahora=t2)
        tiempos.pausar(self.e1, self.j1, ahora=t3)

        resumen = tiempos.resumen_tiempos(self.e1, usuario=self.j1, ahora=t3)
        por_codigo = {e["codigo"]: e for e in resumen["etapas"]}
        self.assertEqual(por_codigo[Etapa.RECOPILACION]["estado"], "Finalizada")
        self.assertEqual(por_codigo[Etapa.RECOPILACION]["duracion_texto"], "2 h 15 min")
        self.assertEqual(por_codigo[Etapa.CONSOLIDACION]["estado"], "En curso")
        self.assertEqual(por_codigo[Etapa.CONSOLIDACION]["duracion_texto"], "1 h 20 min")
        self.assertEqual(por_codigo[Etapa.REVISION]["estado"], "Sin iniciar")
        self.assertEqual(por_codigo[Etapa.REVISION]["duracion_texto"], "0 h 00 min")
        self.assertEqual(resumen["total_texto"], "3 h 35 min")

    def test_ajuste_manual_exige_motivo_y_valida_rango_futuro_y_maximo_12_horas(self):
        ahora = timezone.now().replace(second=0, microsecond=0)
        inicio_ok = ahora - datetime.timedelta(hours=3)
        fin_ok = ahora - datetime.timedelta(hours=1, minutes=30)

        # Sin motivo -> falla.
        for motivo_vacio in ("", "   "):
            with self.subTest(motivo=motivo_vacio):
                with self.assertRaises(ValidationError):
                    tiempos.registrar_manual(
                        self.e1, self.j1, Etapa.RECOPILACION, inicio_ok, fin_ok, motivo_vacio, ahora=ahora
                    )

        # Fin <= inicio -> falla.
        with self.assertRaises(ValidationError):
            tiempos.registrar_manual(
                self.e1, self.j1, Etapa.RECOPILACION, fin_ok, inicio_ok, "Invertido", ahora=ahora
            )
        with self.assertRaises(ValidationError):
            tiempos.registrar_manual(
                self.e1, self.j1, Etapa.RECOPILACION, inicio_ok, inicio_ok, "Cero", ahora=ahora
            )

        # Tiempo en el futuro -> falla.
        with self.assertRaises(ValidationError):
            tiempos.registrar_manual(
                self.e1,
                self.j1,
                Etapa.RECOPILACION,
                ahora - datetime.timedelta(hours=1),
                ahora + datetime.timedelta(minutes=30),
                "Futuro",
                ahora=ahora,
            )

        # Más de 12 horas -> falla.
        with self.assertRaises(ValidationError):
            tiempos.registrar_manual(
                self.e1,
                self.j1,
                Etapa.CONSOLIDACION,
                ahora - datetime.timedelta(hours=13),
                ahora - datetime.timedelta(minutes=30),
                "Demasiado largo",
                ahora=ahora,
            )

        # Válido (<= 12 h, pasado, con motivo) -> se guarda con manual=True y el motivo.
        reg = tiempos.registrar_manual(
            self.e1,
            self.j1,
            Etapa.RECOPILACION,
            inicio_ok,
            fin_ok,
            "Olvidé iniciar el cronómetro",
            ahora=ahora,
        )
        self.assertTrue(reg.manual)
        self.assertEqual(reg.motivo, "Olvidé iniciar el cronómetro")
        self.assertEqual(reg.duracion_texto, "1 h 30 min")

    def test_permisos_para_registrar_tiempo_incluyen_apoyo_activo_y_excluyen_ajenos(self):
        ahora = timezone.now()
        # j2 no es responsable de e1 -> 403 PermissionDenied.
        self.assertFalse(tiempos.puede_registrar_tiempo(self.j2, self.e1))
        with self.assertRaises(PermissionDenied):
            tiempos.iniciar(self.e1, self.j2, Etapa.RECOPILACION, ahora=ahora)

        # Al sumar a j2 como apoyo activo en e1, ya puede registrar tiempo.
        ap = personal.sumar_apoyo(
            self.e1, self.j2, funcion=ResponsableApoyo.Funcion.ELABORACION, autor=self.s1, confirmar=True
        ).objeto
        self.assertTrue(tiempos.puede_registrar_tiempo(self.j2, self.e1))
        reg, _ = tiempos.iniciar(self.e1, self.j2, Etapa.RECOPILACION, ahora=ahora)
        tiempos.pausar(self.e1, self.j2, ahora=ahora + datetime.timedelta(minutes=20))
        self.assertEqual(reg.usuario, self.j2)

        # Al quitar el apoyo, j2 ya no puede iniciar nuevos tramos en e1.
        personal.quitar_apoyo(ap, self.s1)
        self.assertFalse(tiempos.puede_registrar_tiempo(self.j2, self.e1))
        with self.assertRaises(PermissionDenied):
            tiempos.iniciar(self.e1, self.j2, Etapa.CONSOLIDACION, ahora=ahora)


class VisibilidadEHistorialDeTiemposTests(Base):
    """Visibilidad por rol y filtros en `/tiempos/` (§7.7, §8 y `s2-historiales.html`)."""

    def setUp(self):
        super().setUp()
        ahora = timezone.now().replace(second=0, microsecond=0)
        # En e1 (contrato c1 de s1 y j1): registran j1 (1 h) y s1 (0 h 30 min).
        self.r_j1 = tiempos.registrar_manual(
            self.e1,
            self.j1,
            Etapa.RECOPILACION,
            ahora - datetime.timedelta(hours=3),
            ahora - datetime.timedelta(hours=2),
            "Carga inicial j1",
            ahora=ahora,
        )
        self.r_s1 = tiempos.registrar_manual(
            self.e1,
            self.s1,
            Etapa.REVISION,
            ahora - datetime.timedelta(hours=1),
            ahora - datetime.timedelta(minutes=30),
            "Revisión s1",
            ahora=ahora,
        )
        # En e2 (contrato c2 de s2 y j2): registra j2 (2 h).
        self.r_j2 = tiempos.registrar_manual(
            self.e2,
            self.j2,
            Etapa.CONSOLIDACION,
            ahora - datetime.timedelta(hours=4),
            ahora - datetime.timedelta(hours=2),
            "Consolidación j2",
            ahora=ahora,
        )

    def test_cada_rol_ve_solo_los_registros_que_le_corresponden(self):
        # Junior j1: ve SOLO sus propios registros (r_j1), no ve r_s1 (aunque sea en e1) ni r_j2.
        self.assertEqual(set(tiempos.visibles(self.j1)), {self.r_j1})
        self.assertEqual(set(tiempos.visibles(self.j2)), {self.r_j2})

        # Senior s1: ve todos los registros de sus entregables visibles (r_j1 y r_s1 en e1), pero no r_j2 (de e2).
        self.assertEqual(set(tiempos.visibles(self.s1)), {self.r_j1, self.r_s1})
        self.assertEqual(set(tiempos.visibles(self.s2)), {self.r_j2})

        # Gerente y Admin: ven todos (r_j1, r_s1, r_j2).
        for usuario in (self.gerente, self.admin):
            self.assertEqual(set(tiempos.visibles(usuario)), {self.r_j1, self.r_s1, self.r_j2})

    def test_pantalla_tiempos_filtra_muestra_total_y_respeta_html_y_visibilidad(self):
        url = reverse("tiempos")

        # Junior j1 en /tiempos/: solo ve su propio registro (1 h 00 min), no ve el de s1 ni el de j2.
        self.client.force_login(self.j1)
        r_j = self.client.get(url)
        self.assertEqual(r_j.status_code, 200)
        self.assertContains(r_j, "Carga inicial j1")
        self.assertNotContains(r_j, "Revisión s1")
        self.assertNotContains(r_j, "Consolidación j2")
        self.assertContains(r_j, "1 h 00 min")

        # Un filtro por otro responsable (s1) desde la cuenta de j1 nunca amplía su visibilidad.
        r_j_forzado = self.client.get(url, {"responsable": self.s1.pk})
        self.assertNotContains(r_j_forzado, "Revisión s1")

        # Gerente ve los 3 registros (total 3 h 30 min) y puede filtrar por etapa, responsable y fechas.
        self.client.force_login(self.gerente)
        r_g = self.client.get(url)
        self.assertEqual(r_g.status_code, 200)
        html = r_g.content.decode()
        self.assertEqual(html.count("<h1"), 1)
        self.assertNotRegex(html, r"<script>[^<]")
        ids = re.findall(r'\bid="([^"]+)"', html)
        self.assertEqual(len(ids), len(set(ids)), f"IDs repetidos en /tiempos/: {ids}")
        self.assertContains(r_g, "3 h 30 min")

        # Filtro por etapa REVISION -> solo r_s1 (0 h 30 min), también con HTMX.
        r_hx = self.client.get(url, {"etapa": Etapa.REVISION}, HTTP_HX_REQUEST="true")
        self.assertEqual(r_hx.status_code, 200)
        self.assertContains(r_hx, "Revisión s1")
        self.assertNotContains(r_hx, "Carga inicial j1")
        self.assertContains(r_hx, "0 h 30 min")

        # Parámetros inválidos no provocan error 500.
        r_inv = self.client.get(
            url,
            {"cliente": "abc", "etapa": "NO_EXISTE", "responsable": "999999999999999999999", "desde": "mala", "hasta": "2026-99-99"},
        )
        self.assertEqual(r_inv.status_code, 200)

    def test_post_entregable_tiempo_y_detalle_sin_ids_repetidos(self):
        url = reverse("entregable_tiempo", args=[self.e1.pk])

        # Junior ajeno (j2) recibe 404.
        self.client.force_login(self.j2)
        self.assertEqual(self.client.post(url, {"accion": "iniciar", "etapa": Etapa.RECOPILACION}).status_code, 404)

        # Junior asignado (j1) inicia, pausa, finaliza etapa y registra ajuste manual vía POST.
        self.client.force_login(self.j1)
        r_ini = self.client.post(url, {"accion": "iniciar", "etapa": Etapa.CONSOLIDACION})
        self.assertEqual(r_ini.status_code, 302)
        self.assertTrue(r_ini["Location"].endswith("#tiempo"))
        self.assertEqual(RegistroTiempo.objects.filter(usuario=self.j1, fin__isnull=True).count(), 1)

        # El detalle muestra el tramo corriendo y conserva IDs únicos en toda la página.
        r_det = self.client.get(reverse("entregable_detalle", args=[self.e1.pk]))
        self.assertContains(r_det, "Corriendo: Consolidación")
        html_det = r_det.content.decode()
        ids = re.findall(r'\bid="([^"]+)"', html_det)
        self.assertEqual(len(ids), len(set(ids)), f"IDs repetidos en detalle.html: {ids}")

        # Pausar vía HTMX devuelve HX-Redirect a #tiempo.
        r_pausa = self.client.post(url, {"accion": "pausar"}, HTTP_HX_REQUEST="true")
        self.assertEqual(r_pausa.status_code, 200)
        self.assertTrue(r_pausa["HX-Redirect"].endswith("#tiempo"))
        self.assertEqual(RegistroTiempo.objects.filter(usuario=self.j1, fin__isnull=True).count(), 0)

        # Finalizar etapa vía POST.
        r_fin = self.client.post(url, {"accion": "finalizar", "etapa": Etapa.CONSOLIDACION})
        self.assertEqual(r_fin.status_code, 302)
        self.assertTrue(
            RegistroTiempo.objects.filter(entregable=self.e1, etapa=Etapa.CONSOLIDACION, cierra_etapa=True).exists()
        )

        # Ajuste manual vía POST.
        ahora_local = timezone.localtime(timezone.now()).replace(second=0, microsecond=0)
        ini_str = (ahora_local - datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
        fin_str = (ahora_local - datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        r_man = self.client.post(
            url,
            {
                "accion": "manual",
                "etapa": Etapa.RECOPILACION,
                "inicio": ini_str,
                "fin": fin_str,
                "motivo": "Trabajo sin conexión",
            },
        )
        self.assertEqual(r_man.status_code, 302)
        self.assertTrue(
            RegistroTiempo.objects.filter(entregable=self.e1, manual=True, motivo="Trabajo sin conexión").exists()
        )
