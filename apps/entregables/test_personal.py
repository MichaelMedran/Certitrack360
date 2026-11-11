"""Pruebas de gestión de personal, responsables de apoyo, reasignación y conflictos (SDD Sprint 2, RF-31, §6, §7.6, §8, §13 caso 22)."""
import datetime
import importlib
import os
import re
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

import certitrack.settings as modulo_settings
from apps.entregables.testing import aprobar
from apps.alertas.models import Notificacion
from apps.clientes.models import Contrato
from apps.cuentas.models import Ausencia, Usuario
from apps.entregables import adjuntos, filtros, personal, servicios
from apps.entregables.models import Entregable, HistorialEstado, ResponsableApoyo
from apps.entregables.tests import Base
from apps.entregables.visibilidad import (
    entregables_visibles,
    es_apoyo_activo,
    es_elaborador_del_entregable,
    es_responsable_activo,
)

E = Entregable.Estado
F = ResponsableApoyo.Funcion


class ConfiguracionCargaMaximaTests(Base):
    """Configuración CARGA_MAXIMA_ACTIVOS en settings.py y .env.example (§10.1)."""

    def test_valor_por_defecto_y_documentado_en_env_example(self):
        self.assertEqual(settings.CARGA_MAXIMA_ACTIVOS, 8)
        env_example = (settings.BASE_DIR / ".env.example").read_text(encoding="utf-8")
        self.assertIn("CARGA_MAXIMA_ACTIVOS=8", env_example)

    def test_valor_invalido_o_no_positivo_falla_al_arrancar(self):
        for valor in ("0", "-3", "abc"):
            with self.subTest(valor=valor):
                with patch.dict(os.environ, {"CARGA_MAXIMA_ACTIVOS": valor}):
                    with self.assertRaises(ImproperlyConfigured):
                        importlib.reload(modulo_settings)
        importlib.reload(modulo_settings)


class ModelosPersonalTests(Base):
    """Modelos Usuario.puesto, Ausencia y ResponsableApoyo (§6.1 y §6.2)."""

    def test_usuario_tiene_puesto_opcional(self):
        self.assertEqual(self.j1.puesto, "")
        self.j1.puesto = "Analista de cumplimiento"
        self.j1.save(update_fields=["puesto"])
        self.j1.refresh_from_db()
        self.assertEqual(self.j1.puesto, "Analista de cumplimiento")

    def test_ausencia_rechaza_rango_invertido_en_base_de_datos(self):
        hoy = timezone.localdate()
        a = Ausencia.objects.create(
            usuario=self.j1,
            desde=hoy,
            hasta=hoy + datetime.timedelta(days=3),
            motivo="Vacaciones",
            registrada_por=self.gerente,
        )
        self.assertIn("Vacaciones", str(a))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Ausencia.objects.create(
                    usuario=self.j1,
                    desde=hoy + datetime.timedelta(days=5),
                    hasta=hoy + datetime.timedelta(days=2),
                    motivo="Invertida",
                    registrada_por=self.gerente,
                )

    def test_responsable_apoyo_unico_activo_por_entregable_usuario_y_funcion(self):
        ap = ResponsableApoyo.objects.create(
            entregable=self.e1,
            usuario=self.j2,
            funcion=F.ELABORACION,
            asignado_por=self.s1,
            activo=True,
        )
        self.assertIn("elaboración", str(ap).lower())
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ResponsableApoyo.objects.create(
                    entregable=self.e1,
                    usuario=self.j2,
                    funcion=F.ELABORACION,
                    asignado_por=self.s1,
                    activo=True,
                )
        # Otra función activa para el mismo usuario sí se permite.
        ResponsableApoyo.objects.create(
            entregable=self.e1,
            usuario=self.j2,
            funcion=F.APOYO,
            asignado_por=self.s1,
            activo=True,
        )
        # Si se desactiva el primero, se puede volver a crear otro activo con la misma función.
        ap.activo = False
        ap.save(update_fields=["activo"])
        nuevo = ResponsableApoyo.objects.create(
            entregable=self.e1,
            usuario=self.j2,
            funcion=F.ELABORACION,
            asignado_por=self.s1,
            activo=True,
        )
        self.assertTrue(nuevo.activo)


class Caso22ApoyoYReasignacionTests(Base):
    """Caso 22 (§13, RF-31): apoyo ve el entregable pero no aprueba ni devuelve; reasignar deja historial y avisos."""

    def test_apoyo_activo_ve_el_entregable_en_todas_las_vistas_y_filtros(self):
        # Antes de sumarlo como apoyo, j2 no ve e1.
        self.assertNotIn(self.e1, entregables_visibles(self.j2))
        self.client.force_login(self.j2)
        self.assertEqual(self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).status_code, 404)

        res = personal.sumar_apoyo(self.e1, self.j2, funcion=F.ELABORACION, autor=self.s1, confirmar=True)
        self.assertTrue(res.confirmado)
        self.assertTrue(es_apoyo_activo(self.j2, self.e1))
        self.assertTrue(es_elaborador_del_entregable(self.j2, self.e1))
        self.assertTrue(es_responsable_activo(self.j2, self.e1))
        self.assertIn(self.e1, entregables_visibles(self.j2))
        self.assertIn(self.j2, servicios.responsables_posibles(self.e1))

        # j2 ahora ve e1 en el detalle, tablero, listado y calendario.
        self.assertEqual(self.client.get(reverse("entregable_detalle", args=[self.e1.pk])).status_code, 200)
        self.assertContains(self.client.get(reverse("tablero")), self.e1.codigo)
        self.assertContains(self.client.get(reverse("entregables")), self.e1.codigo)

        # El filtro por responsable encuentra e1 cuando se filtra por j2.
        qs, _, _ = filtros.aplicar(entregables_visibles(self.gerente), {"responsable": str(self.j2.pk)})
        self.assertIn(self.e1, qs)

    def test_apoyo_puede_subir_y_enviar_a_revision_pero_no_aprobar_ni_devolver(self):
        personal.sumar_apoyo(self.e1, self.j2, funcion=F.ELABORACION, autor=self.s1, confirmar=True)

        # Puede mover de Por hacer -> En proceso y subir adjuntos.
        self.assertTrue(adjuntos.puede_subir(self.j2, self.e1))
        servicios.mover(self.e1, E.EN_PROCESO, self.j2)
        adjuntos.subir(
            self.e1,
            self.j2,
            SimpleUploadedFile("borrador.pdf", b"%PDF-1.4 apoyo"),
            "BORRADOR",
            comentario="Subido por apoyo",
        )
        # Puede enviar a Revisión senior.
        servicios.mover(self.e1, E.VERIFICACION_SENIOR, self.j2)
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.estado, E.VERIFICACION_SENIOR)

        # NO puede aprobar (pasar a Aprobado) ni devolver a En proceso.
        with self.assertRaises(PermissionDenied):
            servicios.mover(self.e1, E.LISTO_PARA_ENTREGA, self.j2)
        with self.assertRaises(PermissionDenied):
            servicios.mover(self.e1, E.EN_PROCESO, self.j2, observaciones=[{"tipo_error": "FORMATO", "descripcion": "x"}])

        # Incluso si un senior como s2 (ajeno al contrato/entregable) es sumado como apoyo, no puede aprobar e1.
        personal.sumar_apoyo(self.e1, self.s2, funcion=F.REVISION, autor=self.s1, confirmar=True)
        with self.assertRaises(PermissionDenied):
            servicios.mover(self.e1, E.LISTO_PARA_ENTREGA, self.s2)

        # El senior del entregable (s1) sí puede aprobar.
        aprobar(self.e1, self.s1)  # Sprint 3 (RF-45): con la revisión de calidad conforme
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.estado, E.LISTO_PARA_ENTREGA)

    def test_quitar_apoyo_desactiva_sin_borrar_y_retira_visibilidad(self):
        ap = personal.sumar_apoyo(self.e1, self.j2, funcion=F.APOYO, autor=self.s1, confirmar=True).objeto
        self.assertIn(self.e1, entregables_visibles(self.j2))

        personal.quitar_apoyo(ap, self.s1)
        ap.refresh_from_db()
        self.assertFalse(ap.activo)
        self.assertNotIn(self.e1, entregables_visibles(self.j2))
        self.assertTrue(
            HistorialEstado.objects.filter(
                entregable=self.e1,
                detalle__icontains=f"Quitó a {self.j2.nombre} como apoyo (apoyo)",
            ).exists()
        )
        self.assertTrue(
            Notificacion.objects.filter(
                usuario=self.j2,
                entregable=self.e1,
                tipo=Notificacion.Tipo.REASIGNACION,
                mensaje__icontains="Ya no figura como apoyo",
            ).exists()
        )

    def test_reasignar_junior_y_senior_deja_historial_y_notifica_a_quien_entra_y_sale(self):
        res = personal.reasignar_principal(
            self.e1, "junior", self.j2, autor=self.s1, motivo="Vacaciones de j1", confirmar=True
        )
        self.assertTrue(res.confirmado)
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.junior_asignado, self.j2)

        # HistorialEstado registra "Reasignado de j1 a j2" con el motivo.
        h = HistorialEstado.objects.filter(entregable=self.e1).first()
        self.assertIn(f"Reasignado de {self.j1.nombre} a {self.j2.nombre}", h.detalle)
        self.assertIn("Vacaciones de j1", h.detalle)
        self.assertEqual(h.usuario, self.s1)

        # Notificación REASIGNACION tanto a j2 (entra) como a j1 (sale).
        notif_entra = Notificacion.objects.filter(
            usuario=self.j2, entregable=self.e1, tipo=Notificacion.Tipo.REASIGNACION
        ).first()
        notif_sale = Notificacion.objects.filter(
            usuario=self.j1, entregable=self.e1, tipo=Notificacion.Tipo.REASIGNACION
        ).first()
        self.assertIsNotNone(notif_entra)
        self.assertIsNotNone(notif_sale)
        self.assertTrue(notif_entra.enlace.endswith("#responsables"))

        # Reasignar senior_revisor de s1 a s2 por el gerente notifica a ambos.
        res_s = personal.reasignar_principal(self.e1, "senior", self.s2, autor=self.gerente, confirmar=True)
        self.assertTrue(res_s.confirmado)
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.senior_revisor, self.s2)
        self.assertTrue(
            Notificacion.objects.filter(
                usuario=self.s1, entregable=self.e1, tipo=Notificacion.Tipo.REASIGNACION
            ).exists()
        )
        self.assertTrue(
            Notificacion.objects.filter(
                usuario=self.s2, entregable=self.e1, tipo=Notificacion.Tipo.REASIGNACION
            ).exists()
        )

    def test_un_junior_no_puede_reasignar_ni_sumar_o_quitar_apoyo(self):
        ap = personal.sumar_apoyo(self.e1, self.j2, funcion=F.ELABORACION, autor=self.s1, confirmar=True).objeto
        with self.assertRaises(PermissionDenied):
            personal.reasignar_principal(self.e1, "junior", self.j2, autor=self.j1, confirmar=True)
        with self.assertRaises(PermissionDenied):
            personal.sumar_apoyo(self.e1, self.j2, funcion=F.APOYO, autor=self.j1, confirmar=True)
        with self.assertRaises(PermissionDenied):
            personal.quitar_apoyo(ap, self.j1)


class ConflictosAsignacionTests(Base):
    """Detección de los 3 tipos de conflicto (§7.6): sobrecarga, plazo cercano y ausencia."""

    def test_conflicto_por_sobrecarga_al_alcanzar_el_tope(self):
        with override_settings(CARGA_MAXIMA_ACTIVOS=2):
            # j2 tiene 1 activo (e2). Si creamos un segundo activo para j2, al intentar asignarle e1 ya tendría >= 2 otros activos.
            Entregable.objects.create(
                contrato=self.c2,
                plantilla=self.plantilla,
                titulo="Extra activo",
                plazo=self.e1.plazo + datetime.timedelta(days=20),
                junior_asignado=self.j2,
                senior_revisor=self.s2,
                creado_por=self.s2,
            )
            conflictos = personal.detectar_conflictos(self.j2, entregable=self.e1)
            self.assertTrue(any("Sobrecarga" in c for c in conflictos), conflictos)

            # Sin confirmar no guarda; al confirmar sí guarda.
            res_sin = personal.reasignar_principal(self.e1, "junior", self.j2, autor=self.s1, confirmar=False)
            self.assertFalse(res_sin.confirmado)
            self.e1.refresh_from_db()
            self.assertEqual(self.e1.junior_asignado, self.j1)

            res_con = personal.reasignar_principal(self.e1, "junior", self.j2, autor=self.s1, confirmar=True)
            self.assertTrue(res_con.confirmado)
            self.e1.refresh_from_db()
            self.assertEqual(self.e1.junior_asignado, self.j2)

    def test_conflicto_por_plazo_cercano_en_dos_dias(self):
        # e2 tiene el mismo plazo que e1 (ambos a +10 días en Base).
        conflictos = personal.detectar_conflictos(self.j2, entregable=self.e1)
        self.assertTrue(any("Plazo cercano" in c and self.e2.codigo in c for c in conflictos), conflictos)

        # Si el otro entregable vence a más de 2 días, no hay conflicto de plazo cercano.
        self.e2.plazo = self.e1.plazo + datetime.timedelta(days=5)
        self.e2.save(update_fields=["plazo"])
        conflictos_lejos = personal.detectar_conflictos(self.j2, entregable=self.e1)
        self.assertFalse(any("Plazo cercano" in c for c in conflictos_lejos), conflictos_lejos)

    def test_conflicto_por_ausencia_registrada_que_cubre_el_plazo(self):
        self.e2.plazo = self.e1.plazo + datetime.timedelta(days=15)
        self.e2.save(update_fields=["plazo"])
        personal.registrar_ausencia(
            self.j2,
            desde=self.e1.plazo - datetime.timedelta(days=1),
            hasta=self.e1.plazo + datetime.timedelta(days=2),
            motivo="Licencia médica",
            autor=self.gerente,
        )
        conflictos = personal.detectar_conflictos(self.j2, entregable=self.e1)
        self.assertTrue(any("Ausencia registrada" in c and "Licencia médica" in c for c in conflictos), conflictos)


class VistasPersonalYResponsablesTests(Base):
    """Pruebas de vistas HTTP y plantillas para `/personal/` y `/entregables/<pk>/responsables/`."""

    def test_permisos_de_pantalla_personal_por_rol(self):
        url = reverse("personal")
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

        for no_autorizado in (self.j1, self.s1):
            with self.subTest(usuario=no_autorizado.username):
                self.client.force_login(no_autorizado)
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {"accion": "registrar_ausencia"}).status_code, 403)

        for autorizado in (self.gerente, self.admin):
            with self.subTest(usuario=autorizado.username):
                self.client.force_login(autorizado)
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200)
                html = r.content.decode()
                self.assertEqual(html.count("<h1"), 1)
                self.assertNotRegex(html, r"<script>[^<]")
                ids = re.findall(r'\bid="([^"]+)"', html)
                self.assertEqual(len(ids), len(set(ids)), f"IDs repetidos en /personal/: {ids}")

    def test_personal_muestra_carga_filtros_ausencias_y_permite_reasignar_con_aviso(self):
        self.client.force_login(self.gerente)
        url = reverse("personal")

        # Registrar ausencia desde /personal/.
        desde = ( self.e1.plazo - datetime.timedelta(days=1) ).isoformat()
        hasta = ( self.e1.plazo + datetime.timedelta(days=1) ).isoformat()
        r_aus = self.client.post(
            url,
            {
                "accion": "registrar_ausencia",
                "usuario_ausencia": self.j2.pk,
                "desde": desde,
                "hasta": hasta,
                "motivo": "Vacaciones programadas",
            },
            follow=True,
        )
        self.assertEqual(r_aus.status_code, 200)
        self.assertContains(r_aus, "Vacaciones programadas")
        self.assertEqual(Ausencia.objects.filter(usuario=self.j2).count(), 1)

        # Actualizar puesto de j1.
        r_puesto = self.client.post(
            url,
            {"accion": "actualizar_puesto", "usuario_id": self.j1.pk, "puesto": "Analista BPO"},
            follow=True,
        )
        self.assertEqual(r_puesto.status_code, 200)
        self.j1.refresh_from_db()
        self.assertEqual(self.j1.puesto, "Analista BPO")

        # Filtrar por rol y texto.
        r_filtro = self.client.get(url, {"rol": "JUNIOR", "q": "BPO", "colaborador": self.j1.pk})
        self.assertContains(r_filtro, "Analista BPO")
        self.assertNotContains(r_filtro, f"<td>{self.s1.nombre}</td>")

        # Reasignar e1 de j1 a j2 desde /personal/: primero muestra aviso de conflicto (por ausencia y plazo cercano).
        r_conflicto = self.client.post(
            url,
            {
                "accion": "reasignar",
                "entregable_id": self.e1.pk,
                "rol_destino": "junior",
                "nuevo_usuario": self.j2.pk,
                "colaborador": self.j1.pk,
                "motivo": "Cobertura",
            },
        )
        self.assertEqual(r_conflicto.status_code, 200)
        self.assertContains(r_conflicto, "Confirmar de todos modos")
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.junior_asignado, self.j1)

        # Confirmar de todos modos guarda el cambio.
        r_ok = self.client.post(
            url,
            {
                "accion": "reasignar",
                "entregable_id": self.e1.pk,
                "rol_destino": "junior",
                "nuevo_usuario": self.j2.pk,
                "colaborador": self.j1.pk,
                "motivo": "Cobertura",
                "confirmar": "1",
            },
            follow=True,
        )
        self.assertEqual(r_ok.status_code, 200)
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.junior_asignado, self.j2)

    def test_post_entregable_responsables_con_confirmacion_en_dos_pasos_y_permisos(self):
        url = reverse("entregable_responsables", args=[self.e1.pk])

        # Junior principal recibe 403; junior ajeno recibe 404.
        self.client.force_login(self.j1)
        self.assertEqual(self.client.post(url, {"accion": "reasignar", "rol": "junior", "usuario": self.j2.pk}).status_code, 403)
        self.client.force_login(self.j2)
        self.assertEqual(self.client.post(url, {"accion": "reasignar", "rol": "junior", "usuario": self.j2.pk}).status_code, 404)

        # Senior del entregable (s1): e2 de j2 vence el mismo día que e1 -> hay conflicto de plazo cercano.
        self.client.force_login(self.s1)
        r_aviso = self.client.post(url, {"accion": "sumar_apoyo", "usuario": self.j2.pk, "funcion": F.ELABORACION})
        self.assertEqual(r_aviso.status_code, 200)
        self.assertContains(r_aviso, "Antes de confirmar:")
        self.assertContains(r_aviso, "Confirmar de todos modos")
        self.assertEqual(ResponsableApoyo.objects.count(), 0)

        # Segundo clic con confirmar=1 crea el apoyo y redirige a #responsables.
        r_confirmado = self.client.post(
            url,
            {"accion": "sumar_apoyo", "usuario": self.j2.pk, "funcion": F.ELABORACION, "confirmar": "1"},
        )
        self.assertEqual(r_confirmado.status_code, 302)
        self.assertTrue(r_confirmado["Location"].endswith("#responsables"))
        ap = ResponsableApoyo.objects.get(entregable=self.e1, usuario=self.j2, activo=True)

        # Quitar apoyo vía POST.
        r_quitar = self.client.post(url, {"accion": "quitar_apoyo", "apoyo_id": ap.pk})
        self.assertEqual(r_quitar.status_code, 302)
        ap.refresh_from_db()
        self.assertFalse(ap.activo)

    def test_sobrecarga_en_tabla_personal_eliminar_ausencia_y_quitar_apoyo_desde_personal(self):
        self.client.force_login(self.gerente)
        url = reverse("personal")

        # Sumamos a j1 como apoyo de e2 y probamos con CARGA_MAXIMA_ACTIVOS=1 que aparece la etiqueta «Sobrecarga».
        ap = personal.sumar_apoyo(self.e2, self.j1, funcion=F.APOYO, autor=self.gerente, confirmar=True).objeto
        with override_settings(CARGA_MAXIMA_ACTIVOS=1):
            r_sob = self.client.get(url)
            self.assertContains(r_sob, "Sobrecarga")
            self.assertContains(r_sob, "Revisa 1")

        # Quitar el apoyo desde /personal/.
        r_quitar = self.client.post(url, {"accion": "quitar_apoyo", "apoyo_id": ap.pk}, follow=True)
        self.assertEqual(r_quitar.status_code, 200)
        ap.refresh_from_db()
        self.assertFalse(ap.activo)

        # Registrar y luego eliminar una ausencia desde /personal/.
        hoy = timezone.localdate()
        aus = personal.registrar_ausencia(self.j1, hoy, hoy + datetime.timedelta(days=2), "Permiso personal", self.gerente)
        r_del = self.client.post(url, {"accion": "eliminar_ausencia", "ausencia_id": aus.pk}, follow=True)
        self.assertEqual(r_del.status_code, 200)
        self.assertFalse(Ausencia.objects.filter(pk=aus.pk).exists())

    def test_htmx_y_validaciones_en_entregable_responsables(self):
        url = reverse("entregable_responsables", args=[self.e1.pk])
        self.client.force_login(self.s1)

        # Con HTMX devuelve HX-Redirect al confirmar.
        r_hx = self.client.post(
            url,
            {"accion": "sumar_apoyo", "usuario": self.j2.pk, "funcion": F.APOYO, "confirmar": "1"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(r_hx.status_code, 200)
        self.assertTrue(r_hx["HX-Redirect"].endswith("#responsables"))

        # Validaciones: mismo usuario principal, función inválida, fecha inválida, duplicado activo.
        with self.assertRaises(ValidationError):
            personal.reasignar_principal(self.e1, "junior", self.j1, autor=self.s1, confirmar=True)
        with self.assertRaises(ValidationError):
            personal.reasignar_principal(self.e1, "rol_invalido", self.j2, autor=self.s1, confirmar=True)
        with self.assertRaises(ValidationError):
            personal.sumar_apoyo(self.e1, self.j2, funcion=F.APOYO, autor=self.s1, confirmar=True)
        with self.assertRaises(ValidationError):
            personal.sumar_apoyo(self.e1, self.j2, funcion="NO_EXISTE", autor=self.s1, confirmar=True)
        with self.assertRaises(ValidationError):
            personal.sumar_apoyo(self.e1, self.j2, funcion=F.REVISION, fecha_limite="fecha-mala", autor=self.s1, confirmar=True)
        with self.assertRaises(ValidationError):
            personal.registrar_ausencia(self.j1, "2026-05-10", "2026-05-01", "Invertida", self.gerente)
        with self.assertRaises(ValidationError):
            personal.registrar_ausencia(self.j1, "2026-05-01", "2026-05-10", "   ", self.gerente)
        with self.assertRaises(PermissionDenied):
            personal.registrar_ausencia(self.j1, "2026-05-01", "2026-05-10", "Motivo", self.s1)
