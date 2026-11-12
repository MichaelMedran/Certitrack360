"""Pruebas del hito S2-H5 · RF-30 (HU-14 y HU-06): ficha de levantamiento del TDR, vista previa, generación de entregables
con Poka-Yoke, estado documental inicial congelado y permisos por rol (Caso 21 del SDD del Sprint 2, §13)."""
import copy
import datetime
import importlib
import os
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.alertas.models import Notificacion
from apps.clientes.models import Cliente, Contrato, PlantillaTDR
from apps.cuentas.models import Usuario
from apps.entregables.models import Entregable, HistorialEstado
from apps.entregables.testing import MediaTemporal
from apps.entregables.tests import Base

from . import filtros, servicios
from .models import FichaLevantamiento, ItemFicha
from .visibilidad import contratos_para_ficha, fichas_visibles


def archivo_pdf(nombre="tdr_contrato.pdf", contenido=b"%PDF-1.4 contenido del TDR"):
    return SimpleUploadedFile(nombre, contenido, content_type="application/pdf")


class ConfiguracionFichaTests(SimpleTestCase):
    def test_ficha_max_entregables_por_defecto_y_en_env_example(self):
        self.assertEqual(settings.FICHA_MAX_ENTREGABLES, 60)
        ejemplo = (Path(settings.BASE_DIR) / ".env.example").read_text(encoding="utf-8")
        self.assertIn("FICHA_MAX_ENTREGABLES=60", ejemplo)

    def test_ficha_max_entregables_no_positivo_se_rechaza(self):
        import certitrack.settings as mod_settings

        for valor in ("0", "-5"):
            with self.subTest(valor=valor):
                with mock.patch.dict(os.environ, {"FICHA_MAX_ENTREGABLES": valor}):
                    with self.assertRaises(ImproperlyConfigured):
                        importlib.reload(mod_settings)
        importlib.reload(mod_settings)


class FichaBase(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.hoy = timezone.localdate()
        # Asegura que el contrato c1 tenga fecha_fin amplia en el futuro para pruebas de recurrencia.
        Contrato.objects.filter(pk=cls.c1.pk).update(
            fecha_inicio=cls.hoy - datetime.timedelta(days=60),
            fecha_fin=cls.hoy + datetime.timedelta(days=400),
        )
        Contrato.objects.filter(pk=cls.c2.pk).update(
            fecha_inicio=cls.hoy - datetime.timedelta(days=60),
            fecha_fin=cls.hoy + datetime.timedelta(days=400),
        )
        cls.c1.refresh_from_db()
        cls.c2.refresh_from_db()
        cls.plantilla_matriz = PlantillaTDR.objects.create(
            nombre="Matriz de riesgos",
            campos_requeridos=[
                {"nombre": "c_responsable_del_cliente", "etiqueta": "Responsable del cliente", "tipo": "texto"},
            ],
        )

    def crear_ficha_borrador(self, contrato=None, creador=None, responsable=None, **campos):
        contrato = contrato or self.c1
        creador = creador or self.j1
        responsable = responsable or self.j1
        archivo = campos.pop("archivo_tdr", None) or archivo_pdf()
        datos = {
            "contrato": contrato,
            "id_tdr": "TDR-BAF-020",
            "archivo_tdr": archivo,
            "nombre_archivo_tdr": archivo.name,
            "requerimientos": "Digitalizar y reportar avance de expedientes.",
            "formatos": "Reporte mensual en PDF, matriz en Excel",
            "frecuencia_reportes": "Mensual",
            "penalidades": "1 % del monto mensual por día de retraso",
            "responsable": responsable,
            "documentos_disponibles": "Contrato firmado, TDR, cronograma",
            "documentos_faltantes": "Carta de designación del cliente",
            "formato_esperado": "PDF firmado",
            "fecha_limite": self.hoy + datetime.timedelta(days=15),
            "creada_por": creador,
        }
        datos.update(campos)
        return FichaLevantamiento.objects.create(**datos)

    def agregar_item(self, ficha, **campos):
        primera = campos.pop("primera_fecha", self.hoy + datetime.timedelta(days=5))
        datos = {
            "ficha": ficha,
            "nombre": "Reporte mensual",
            "plantilla": self.plantilla,
            "frecuencia": ItemFicha.Frecuencia.MENSUAL,
            "primera_fecha": primera,
            "hasta": servicios._sumar_meses(primera, 2),
            "junior": self.j1,
            "senior": self.s1,
            "datos": {"c_periodo": "2026-12", "c_nivel": "1"},
        }
        datos.update(campos)
        return ItemFicha.objects.create(**datos)


class Caso21GeneracionDeEntregablesTests(FichaBase):
    """Caso 21 (§13): una ficha mensual de 3 meses genera 3 entregables visibles en tablero y calendario,
    descarta plazos pasados, valida obligatorios y conserva la foto inicial."""

    def test_caso_21_ficha_mensual_de_3_meses_genera_3_entregables_visibles_en_tablero_y_calendario(self):
        ficha = self.crear_ficha_borrador()
        primera = self.hoy + datetime.timedelta(days=5)
        item = self.agregar_item(
            ficha,
            nombre="Reporte mensual",
            frecuencia=ItemFicha.Frecuencia.MENSUAL,
            primera_fecha=primera,
            hasta=servicios._sumar_meses(primera, 2),
        )

        self.client.force_login(self.s1)
        r_previa = self.client.post(reverse("ficha_vista_previa", args=[ficha.pk]))
        self.assertEqual(r_previa.status_code, 200)
        self.assertEqual(r_previa.context["vista_previa"]["total"], 3)
        self.assertEqual(r_previa.context["vista_previa"]["omitidas"], 0)

        r_conf = self.client.post(reverse("ficha_confirmar", args=[ficha.pk]), follow=True)
        self.assertRedirects(r_conf, reverse("ficha_detalle", args=[ficha.pk]))
        self.assertContains(r_conf, "Ficha confirmada: se generaron 3 entregables.")

        ficha.refresh_from_db()
        self.assertTrue(ficha.confirmada)
        self.assertEqual(ficha.confirmada_por, self.s1)
        self.assertIsNotNone(ficha.confirmada_en)

        generados = list(item.entregables_generados.order_by("plazo"))
        self.assertEqual(len(generados), 3)
        fechas_esperadas = [primera, servicios._sumar_meses(primera, 1), servicios._sumar_meses(primera, 2)]
        self.assertEqual([e.plazo for e in generados], fechas_esperadas)
        self.assertEqual([e.titulo for e in generados], [f"Reporte mensual — {f:%Y-%m}" for f in fechas_esperadas])
        self.assertEqual(len({e.codigo for e in generados}), 3)

        for e in generados:
            self.assertTrue(e.codigo.startswith(f"{settings.CODIGO_PREFIJO}-"))
            self.assertEqual(e.id_tdr, "TDR-BAF-020")
            self.assertEqual(e.fecha_recepcion, self.hoy)
            self.assertEqual(e.datos, {"c_periodo": "2026-12", "c_nivel": "1"})
            self.assertTrue(
                HistorialEstado.objects.filter(
                    entregable=e, estado_nuevo=Entregable.Estado.A_REALIZAR, detalle="Entregable creado"
                ).exists()
            )
            self.assertTrue(
                Notificacion.objects.filter(
                    usuario=self.j1, entregable=e, tipo=Notificacion.Tipo.ASIGNACION
                ).exists()
            )

        # Visibles en el tablero y en el calendario para el junior asignado y el senior.
        for usuario in (self.j1, self.s1, self.gerente):
            self.client.force_login(usuario)
            html_tablero = self.client.get(reverse("tablero")).content.decode()
            eventos = self.client.get(reverse("calendario_eventos")).json()
            titulos_cal = " ".join(ev["title"] for ev in eventos)
            for e in generados:
                self.assertIn(e.codigo, html_tablero)
                self.assertIn(e.titulo, html_tablero)
                self.assertIn(e.codigo, titulos_cal)

    def test_frecuencias_unica_semanal_quincenal_mensual_y_trimestral(self):
        ficha = self.crear_ficha_borrador()
        inicio = datetime.date(2027, 1, 31)
        Contrato.objects.filter(pk=self.c1.pk).update(fecha_fin=datetime.date(2027, 10, 31))
        self.c1.refresh_from_db()
        ficha.contrato = self.c1

        it_unica = self.agregar_item(
            ficha, nombre="Plan de trabajo", frecuencia=ItemFicha.Frecuencia.UNICA,
            primera_fecha=inicio, hasta=datetime.date(2027, 5, 1),
        )
        self.assertEqual(servicios.fechas_item(it_unica), [(inicio, "Plan de trabajo")])

        it_sem = self.agregar_item(
            ficha, nombre="Avance semanal", frecuencia=ItemFicha.Frecuencia.SEMANAL,
            primera_fecha=datetime.date(2027, 1, 1), hasta=datetime.date(2027, 1, 15),
        )
        self.assertEqual(
            servicios.fechas_item(it_sem),
            [
                (datetime.date(2027, 1, 1), "Avance semanal — 2027-01-01"),
                (datetime.date(2027, 1, 8), "Avance semanal — 2027-01-08"),
                (datetime.date(2027, 1, 15), "Avance semanal — 2027-01-15"),
            ],
        )

        it_quin = self.agregar_item(
            ficha, nombre="Corte quincenal", frecuencia=ItemFicha.Frecuencia.QUINCENAL,
            primera_fecha=datetime.date(2027, 1, 1), hasta=datetime.date(2027, 1, 31),
        )
        self.assertEqual(
            servicios.fechas_item(it_quin),
            [
                (datetime.date(2027, 1, 1), "Corte quincenal — 2027-01-01"),
                (datetime.date(2027, 1, 16), "Corte quincenal — 2027-01-16"),
                (datetime.date(2027, 1, 31), "Corte quincenal — 2027-01-31"),
            ],
        )

        # Mensual con día 31: se ajusta al último día de febrero y abril.
        it_men = self.agregar_item(
            ficha, nombre="Informe mensual", frecuencia=ItemFicha.Frecuencia.MENSUAL,
            primera_fecha=inicio, hasta=datetime.date(2027, 4, 30),
        )
        self.assertEqual(
            servicios.fechas_item(it_men),
            [
                (datetime.date(2027, 1, 31), "Informe mensual — 2027-01"),
                (datetime.date(2027, 2, 28), "Informe mensual — 2027-02"),
                (datetime.date(2027, 3, 31), "Informe mensual — 2027-03"),
                (datetime.date(2027, 4, 30), "Informe mensual — 2027-04"),
            ],
        )

        # Trimestral sin «hasta»: usa fecha_fin del contrato.
        it_trim = self.agregar_item(
            ficha, nombre="Matriz de avance", frecuencia=ItemFicha.Frecuencia.TRIMESTRAL,
            primera_fecha=datetime.date(2027, 1, 15), hasta=None,
        )
        self.assertEqual(
            servicios.fechas_item(it_trim),
            [
                (datetime.date(2027, 1, 15), "Matriz de avance — 2027-T1"),
                (datetime.date(2027, 4, 15), "Matriz de avance — 2027-T2"),
                (datetime.date(2027, 7, 15), "Matriz de avance — 2027-T3"),
                (datetime.date(2027, 10, 15), "Matriz de avance — 2027-T4"),
            ],
        )

    def test_frecuencias_bimestral_y_semestral(self):
        ficha = self.crear_ficha_borrador()
        Contrato.objects.filter(pk=self.c1.pk).update(fecha_fin=datetime.date(2028, 3, 31))
        self.c1.refresh_from_db()
        ficha.contrato = self.c1

        # Bimestral con día 31: se ajusta al último día de los meses más cortos.
        it_bim = self.agregar_item(
            ficha, nombre="Reporte bimestral", frecuencia=ItemFicha.Frecuencia.BIMESTRAL,
            primera_fecha=datetime.date(2027, 8, 31), hasta=datetime.date(2028, 2, 29),
        )
        self.assertEqual(
            servicios.fechas_item(it_bim),
            [
                (datetime.date(2027, 8, 31), "Reporte bimestral — 2027-B4"),
                (datetime.date(2027, 10, 31), "Reporte bimestral — 2027-B5"),
                (datetime.date(2027, 12, 31), "Reporte bimestral — 2027-B6"),
                (datetime.date(2028, 2, 29), "Reporte bimestral — 2028-B1"),
            ],
        )

        # Semestral sin «hasta»: usa fecha_fin del contrato.
        it_sem = self.agregar_item(
            ficha, nombre="Informe semestral", frecuencia=ItemFicha.Frecuencia.SEMESTRAL,
            primera_fecha=datetime.date(2027, 1, 15), hasta=None,
        )
        self.assertEqual(
            servicios.fechas_item(it_sem),
            [
                (datetime.date(2027, 1, 15), "Informe semestral — 2027-S1"),
                (datetime.date(2027, 7, 15), "Informe semestral — 2027-S2"),
                (datetime.date(2028, 1, 15), "Informe semestral — 2028-S1"),
            ],
        )

    def test_caso_21_plazos_pasados_se_descartan_con_aviso(self):
        ficha = self.crear_ficha_borrador()
        hace_dos_semanas = self.hoy - datetime.timedelta(days=14)
        en_una_semana = self.hoy + datetime.timedelta(days=7)
        self.agregar_item(
            ficha,
            nombre="Reporte semanal",
            frecuencia=ItemFicha.Frecuencia.SEMANAL,
            primera_fecha=hace_dos_semanas,
            hasta=en_una_semana,
        )

        self.client.force_login(self.s1)
        r_previa = self.client.post(reverse("ficha_vista_previa", args=[ficha.pk]))
        self.assertContains(r_previa, "Se omitieron 2 fechas pasadas. Total: 2 entregables")
        self.assertEqual(r_previa.context["vista_previa"]["omitidas"], 2)
        self.assertEqual(r_previa.context["vista_previa"]["total"], 2)

        r_conf = self.client.post(reverse("ficha_confirmar", args=[ficha.pk]), follow=True)
        self.assertContains(r_conf, "Ficha confirmada: se generaron 2 entregables. Se omitieron 2 fechas pasadas.")

    def test_quitar_entregables_en_vista_previa_antes_de_confirmar(self):
        ficha = self.crear_ficha_borrador()
        primera = self.hoy + datetime.timedelta(days=3)
        item = self.agregar_item(
            ficha,
            nombre="Reporte mensual",
            frecuencia=ItemFicha.Frecuencia.MENSUAL,
            primera_fecha=primera,
            hasta=servicios._sumar_meses(primera, 2),
        )
        self.client.force_login(self.s1)
        # Quitar el segundo entregable (índice 1) en la vista previa y confirmar.
        r_previa = self.client.post(reverse("ficha_vista_previa", args=[ficha.pk]), {"excluir": ["1"]})
        self.assertEqual(r_previa.context["vista_previa"]["total"], 2)
        self.assertEqual(r_previa.context["vista_previa"]["indices_excluidos"], ["1"])

        self.client.post(reverse("ficha_confirmar", args=[ficha.pk]), {"excluir": ["1"]})
        plazos = [e.plazo for e in item.entregables_generados.order_by("plazo")]
        self.assertEqual(plazos, [primera, servicios._sumar_meses(primera, 2)])

    @override_settings(FICHA_MAX_ENTREGABLES=2)
    def test_limite_ficha_max_entregables_impide_confirmar(self):
        ficha = self.crear_ficha_borrador()
        primera = self.hoy + datetime.timedelta(days=2)
        item = self.agregar_item(
            ficha,
            frecuencia=ItemFicha.Frecuencia.MENSUAL,
            primera_fecha=primera,
            hasta=servicios._sumar_meses(primera, 2),
        )
        self.client.force_login(self.s1)
        r_previa = self.client.post(reverse("ficha_vista_previa", args=[ficha.pk]))
        self.assertTrue(r_previa.context["vista_previa"]["excede_maximo"])
        self.assertContains(r_previa, "La ficha generaría 3 entregables y el máximo permitido por confirmación es 2.")

        r_conf = self.client.post(reverse("ficha_confirmar", args=[ficha.pk]))
        self.assertContains(r_conf, "La ficha generaría 3 entregables y el máximo permitido por confirmación es 2.")
        ficha.refresh_from_db()
        self.assertFalse(ficha.confirmada)
        self.assertEqual(item.entregables_generados.count(), 0)

    def test_no_se_puede_confirmar_dos_veces(self):
        ficha = self.crear_ficha_borrador()
        self.agregar_item(ficha)
        servicios.confirmar(ficha, self.s1)
        with self.assertRaisesMessage(ValidationError, "Esta ficha ya fue confirmada."):
            servicios.confirmar(ficha, self.s1)


class Caso21ValidacionPokaYokeTests(FichaBase):
    """Validación Poka-Yoke de los campos obligatorios de la ficha, archivo del TDR y campos de plantilla por ítem."""

    def datos_post(self, **cambios):
        primera = (self.hoy + datetime.timedelta(days=5)).isoformat()
        hasta = (self.hoy + datetime.timedelta(days=65)).isoformat()
        base = {
            "contrato": str(self.c1.pk),
            "id_tdr": "TDR-BAF-020",
            "archivo_tdr": archivo_pdf(),
            "requerimientos": "Digitalizar expedientes.",
            "formatos": "PDF",
            "frecuencia_reportes": "Mensual",
            "penalidades": "1 % por día",
            "responsable": str(self.j1.pk),
            "documentos_disponibles": "Contrato, TDR",
            "documentos_faltantes": "Carta",
            "formato_esperado": "PDF firmado",
            "fecha_limite": (self.hoy + datetime.timedelta(days=15)).isoformat(),
            "estado_documental": "ABIERTO",
            "item_nombre": ["Reporte mensual"],
            "item_plantilla": [str(self.plantilla.pk)],
            "item_frecuencia": ["MENSUAL"],
            "item_primera_fecha": [primera],
            "item_hasta": [hasta],
            "item_junior": [str(self.j1.pk)],
            "item_senior": [str(self.s1.pk)],
            f"item_dato_{self.plantilla.pk}_c_periodo": ["2026-12"],
            f"item_dato_{self.plantilla.pk}_c_nivel": ["2"],
        }
        base.update(cambios)
        return base

    def test_alta_por_formulario_guarda_ficha_e_items(self):
        self.client.force_login(self.j1)
        r = self.client.post(reverse("ficha_nueva"), self.datos_post(), follow=True)
        self.assertEqual(r.status_code, 200)
        ficha = FichaLevantamiento.objects.get(id_tdr="TDR-BAF-020")
        self.assertEqual(ficha.estado, FichaLevantamiento.Estado.BORRADOR)
        self.assertEqual(ficha.items.count(), 1)
        item = ficha.items.first()
        self.assertEqual(item.datos, {"c_periodo": "2026-12", "c_nivel": "2"})

    def test_campos_obligatorios_de_la_ficha_se_validan_con_mensajes_claros(self):
        self.client.force_login(self.s1)
        url = reverse("ficha_nueva")

        casos = [
            ({"contrato": ""}, "Falta elegir el contrato."),
            ({"id_tdr": "   "}, "Falta el ID-TDR."),
            ({"archivo_tdr": ""}, "Falta adjuntar el archivo del TDR."),
            ({"requerimientos": "  "}, "Falta indicar los requerimientos del servicio."),
            ({"responsable": ""}, "Falta elegir el responsable de la ficha."),
            (
                {
                    "item_nombre": [""],
                    "item_plantilla": [""],
                    "item_primera_fecha": [""],
                    "item_hasta": [""],
                    "item_junior": [""],
                    f"item_dato_{self.plantilla.pk}_c_periodo": [""],
                    f"item_dato_{self.plantilla.pk}_c_nivel": [""],
                },
                "Debe registrar al menos un entregable en la ficha.",
            ),
        ]
        for cambios, esperado in casos:
            with self.subTest(esperado=esperado):
                r = self.client.post(url, self.datos_post(**cambios))
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, esperado)
        self.assertEqual(FichaLevantamiento.objects.count(), 0)

    def test_archivo_tdr_se_valida_con_validar_archivo(self):
        self.client.force_login(self.s1)
        malo = SimpleUploadedFile("script.exe", b"binario", content_type="application/octet-stream")
        r = self.client.post(reverse("ficha_nueva"), self.datos_post(archivo_tdr=malo))
        self.assertContains(r, "El archivo «script.exe» no es de un tipo permitido.")
        self.assertEqual(FichaLevantamiento.objects.count(), 0)

    def test_falta_campo_obligatorio_de_la_plantilla_nombra_el_item_y_el_campo(self):
        self.client.force_login(self.s1)
        datos = self.datos_post(
            item_nombre=["Matriz de avance"],
            item_plantilla=[str(self.plantilla_matriz.pk)],
            **{f"item_dato_{self.plantilla_matriz.pk}_c_responsable_del_cliente": [""]},
        )
        r = self.client.post(reverse("ficha_nueva"), datos)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "En «Matriz de avance» falta completar el campo «Responsable del cliente».")

        # También si el ítem en base de datos tiene el dato incompleto al pedir vista previa o confirmar.
        ficha = self.crear_ficha_borrador()
        self.agregar_item(
            ficha,
            nombre="Matriz de avance",
            plantilla=self.plantilla_matriz,
            datos={},
        )
        r_prev = self.client.post(reverse("ficha_vista_previa", args=[ficha.pk]))
        self.assertContains(
            r_prev,
            "No se puede generar la vista previa: En «Matriz de avance» falta completar el campo «Responsable del cliente».",
        )
        r_conf = self.client.post(reverse("ficha_confirmar", args=[ficha.pk]))
        self.assertContains(r_conf, "En «Matriz de avance» falta completar el campo «Responsable del cliente».")
        ficha.refresh_from_db()
        self.assertFalse(ficha.confirmada)

    def test_validaciones_de_fechas_y_junior_del_contrato_en_item(self):
        self.client.force_login(self.s1)
        primera = (self.hoy + datetime.timedelta(days=20)).isoformat()
        antes = (self.hoy + datetime.timedelta(days=5)).isoformat()
        r = self.client.post(
            reverse("ficha_nueva"),
            self.datos_post(item_nombre=["Reporte A"], item_primera_fecha=[primera], item_hasta=[antes]),
        )
        self.assertContains(r, "En «Reporte A» la fecha final («Hasta») no puede ser anterior a la primera fecha.")

        # j2 no está asignado a c1
        r_jr = self.client.post(
            reverse("ficha_nueva"),
            self.datos_post(item_nombre=["Reporte A"], item_junior=[str(self.j2.pk)]),
        )
        self.assertContains(r_jr, f"En «Reporte A» el junior {self.j2.nombre} no está asignado al contrato elegido.")


class Caso21EstadoInicialCongeladoTests(FichaBase):
    """HU-06 y Caso 21: `estado_inicial` guarda la foto al confirmar y nunca se sobrescribe al actualizar el estado documental."""

    def test_caso_21_estado_inicial_se_congela_al_confirmar_y_nunca_cambia(self):
        ficha = self.crear_ficha_borrador(
            documentos_disponibles="Contrato firmado, TDR, cronograma",
            documentos_faltantes="Carta de designación del cliente",
            formato_esperado="PDF firmado",
        )
        self.agregar_item(ficha)
        servicios.confirmar(ficha, self.s1)
        ficha.refresh_from_db()

        foto_original = copy.deepcopy(ficha.estado_inicial)
        self.assertEqual(set(foto_original.keys()), set(servicios.CAMPOS_ESTADO_INICIAL))
        self.assertEqual(foto_original["id_tdr"], "TDR-BAF-020")
        self.assertEqual(foto_original["documentos_disponibles"], "Contrato firmado, TDR, cronograma")
        self.assertEqual(foto_original["documentos_faltantes"], "Carta de designación del cliente")
        self.assertEqual(foto_original["formato_esperado"], "PDF firmado")
        self.assertEqual(foto_original["responsable"], self.j1.nombre)

        # Actualizar estado documental actual desde la vista POST /fichas/<id>/
        self.client.force_login(self.j1)
        nueva_fecha = self.hoy + datetime.timedelta(days=30)
        r = self.client.post(
            reverse("ficha_detalle", args=[ficha.pk]),
            {
                "documentos_disponibles": "Contrato firmado, TDR, cronograma, carta de designación",
                "documentos_faltantes": "",
                "formato_esperado": "PDF con firma digital",
                "fecha_limite": nueva_fecha.isoformat(),
                "estado_documental": FichaLevantamiento.EstadoDocumental.COMPLETO,
            },
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Se actualizó el estado documental actual. El estado inicial permanece intacto.")

        ficha.refresh_from_db()
        self.assertEqual(ficha.estado_documental, FichaLevantamiento.EstadoDocumental.COMPLETO)
        self.assertEqual(ficha.documentos_disponibles, "Contrato firmado, TDR, cronograma, carta de designación")
        self.assertEqual(ficha.documentos_faltantes, "")
        self.assertEqual(ficha.formato_esperado, "PDF con firma digital")
        self.assertEqual(ficha.fecha_limite, nueva_fecha)
        # La foto inicial jamás cambia:
        self.assertEqual(ficha.estado_inicial, foto_original)

        # Incluso si alguien intenta alterar `estado_inicial` en memoria y llamar a save():
        ficha.estado_inicial = {"documentos_disponibles": "Alterado"}
        ficha.save()
        ficha.refresh_from_db()
        self.assertEqual(ficha.estado_inicial, foto_original)

        # La pantalla muestra tanto el estado inicial congelado como el estado actual:
        html = r.content.decode()
        self.assertIn("Carta de designación del cliente", html)
        self.assertIn("Contrato firmado, TDR, cronograma, carta de designación", html)


class PermisosYVisibilidadTests(FichaBase):
    """Permisos y visibilidad por rol (§7.5, §8, decisión C7)."""

    def setUp(self):
        super().setUp()
        self.ficha_c1 = self.crear_ficha_borrador(contrato=self.c1, creador=self.j1, responsable=self.j1, id_tdr="TDR-C1")
        self.agregar_item(self.ficha_c1, junior=self.j1, senior=self.s1)

        self.ficha_c2 = self.crear_ficha_borrador(contrato=self.c2, creador=self.j2, responsable=self.j2, id_tdr="TDR-C2")
        self.agregar_item(self.ficha_c2, junior=self.j2, senior=self.s2)

    def test_visibilidad_de_fichas_y_contratos_por_rol(self):
        self.assertEqual(set(fichas_visibles(self.j1)), {self.ficha_c1})
        self.assertEqual(set(fichas_visibles(self.j2)), {self.ficha_c2})
        self.assertEqual(set(fichas_visibles(self.s1)), {self.ficha_c1})
        self.assertEqual(set(fichas_visibles(self.s2)), {self.ficha_c2})
        self.assertEqual(set(fichas_visibles(self.gerente)), {self.ficha_c1, self.ficha_c2})
        self.assertEqual(set(fichas_visibles(self.admin)), {self.ficha_c1, self.ficha_c2})

        self.assertEqual(set(contratos_para_ficha(self.j1)), {self.c1})
        self.assertEqual(set(contratos_para_ficha(self.s1)), {self.c1})
        self.assertEqual(set(contratos_para_ficha(self.gerente)), {self.c1, self.c2})

    def test_junior_redacta_y_pide_confirmacion_pero_no_puede_confirmar_403(self):
        self.client.force_login(self.j1)
        # Pedir confirmación avisa al senior responsable del contrato (notificación sin entregable con enlace a la ficha).
        r_pedir = self.client.post(
            reverse("ficha_confirmar", args=[self.ficha_c1.pk]),
            {"accion": "pedir_confirmacion"},
            follow=True,
        )
        self.assertEqual(r_pedir.status_code, 200)
        aviso = Notificacion.objects.filter(usuario=self.s1, tipo=Notificacion.Tipo.FICHA).first()
        self.assertIsNotNone(aviso)
        self.assertIsNone(aviso.entregable)
        self.assertEqual(aviso.enlace, reverse("ficha_detalle", args=[self.ficha_c1.pk]))
        self.assertEqual(aviso.destino, reverse("ficha_detalle", args=[self.ficha_c1.pk]))

        # Intentar confirmar directamente como junior responde 403 y no crea entregables.
        r_conf = self.client.post(reverse("ficha_confirmar", args=[self.ficha_c1.pk]))
        self.assertEqual(r_conf.status_code, 403)
        self.ficha_c1.refresh_from_db()
        self.assertFalse(self.ficha_c1.confirmada)

    def test_acceso_a_ficha_ajena_responde_404_en_todas_las_rutas(self):
        for usuario in (self.j2, self.s2):
            self.client.force_login(usuario)
            for ruta, metodo in (
                (reverse("ficha_detalle", args=[self.ficha_c1.pk]), "get"),
                (reverse("ficha_detalle", args=[self.ficha_c1.pk]), "post"),
                (reverse("ficha_vista_previa", args=[self.ficha_c1.pk]), "post"),
                (reverse("ficha_confirmar", args=[self.ficha_c1.pk]), "post"),
                (reverse("ficha_archivo", args=[self.ficha_c1.pk]), "get"),
            ):
                with self.subTest(usuario=usuario.username, ruta=ruta, metodo=metodo):
                    r = getattr(self.client, metodo)(ruta)
                    self.assertEqual(r.status_code, 404)

    def test_senior_que_es_responsable_de_ficha_pero_no_del_contrato_no_puede_confirmar_403(self):
        FichaLevantamiento.objects.filter(pk=self.ficha_c1.pk).update(responsable=self.s2)
        self.client.force_login(self.s2)
        self.assertEqual(self.client.get(reverse("ficha_detalle", args=[self.ficha_c1.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("ficha_confirmar", args=[self.ficha_c1.pk])).status_code, 403)

    def test_descarga_controlada_del_archivo_tdr(self):
        self.client.force_login(self.j1)
        r = self.client.get(reverse("ficha_archivo", args=[self.ficha_c1.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertIn("no-store", r["Cache-Control"])
        self.assertIn("tdr_contrato.pdf", r["Content-Disposition"])
        r.close()

    def test_listado_y_filtros_por_cliente_contrato_y_estado(self):
        otro_cliente = Cliente.objects.create(nombre="Otro Cliente", sector="TELECOM")
        Contrato.objects.filter(pk=self.c2.pk).update(cliente=otro_cliente)
        servicios.confirmar(self.ficha_c1, self.s1)
        servicios.actualizar_estado_documental(
            self.ficha_c1, self.s1, estado_documental=FichaLevantamiento.EstadoDocumental.EN_CURSO
        )

        self.client.force_login(self.gerente)
        r = self.client.get(reverse("fichas"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["fichas"]), 2)

        # Filtro por cliente, contrato, estado de ficha y estado documental
        self.assertEqual(
            [f.pk for f in self.client.get(reverse("fichas"), {"cliente": self.cliente.pk}).context["fichas"]],
            [self.ficha_c1.pk],
        )
        self.assertEqual(
            [f.pk for f in self.client.get(reverse("fichas"), {"contrato": self.c2.pk}).context["fichas"]],
            [self.ficha_c2.pk],
        )
        self.assertEqual(
            [f.pk for f in self.client.get(reverse("fichas"), {"estado": "CONFIRMADA"}).context["fichas"]],
            [self.ficha_c1.pk],
        )
        self.assertEqual(
            [f.pk for f in self.client.get(reverse("fichas"), {"estado": "EN_CURSO"}).context["fichas"]],
            [self.ficha_c1.pk],
        )
        # Los filtros nunca amplían la visibilidad y los ids fuera de rango se ignoran sin error 500
        self.client.force_login(self.j1)
        self.assertEqual(
            self.client.get(reverse("fichas"), {"contrato": self.c2.pk}).context["fichas"],
            [],
        )
        for valor in ("abc", str(2**63), "9" * 200):
            self.assertEqual(self.client.get(reverse("fichas"), {"cliente": valor, "contrato": valor}).status_code, 200)

    def test_exige_csrf_en_escrituras(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.s1)
        self.assertEqual(c.post(reverse("ficha_confirmar", args=[self.ficha_c1.pk])).status_code, 403)
        self.ficha_c1.refresh_from_db()
        self.assertFalse(self.ficha_c1.confirmada)

    def test_sin_sesion_redirige_al_ingreso(self):
        self.client.logout()
        for ruta, metodo in (
            (reverse("fichas"), "get"),
            (reverse("ficha_nueva"), "get"),
            (reverse("ficha_detalle", args=[self.ficha_c1.pk]), "get"),
            (reverse("ficha_vista_previa", args=[self.ficha_c1.pk]), "post"),
            (reverse("ficha_confirmar", args=[self.ficha_c1.pk]), "post"),
            (reverse("ficha_archivo", args=[self.ficha_c1.pk]), "get"),
        ):
            with self.subTest(ruta=ruta, metodo=metodo):
                r = getattr(self.client, metodo)(ruta)
                self.assertEqual(r.status_code, 302)
                self.assertTrue(r["Location"].startswith(reverse("login")))

    def test_editar_borrador_conserva_el_archivo_si_no_se_sube_otro_y_permite_vista_previa(self):
        self.client.force_login(self.j1)
        primera = (self.hoy + datetime.timedelta(days=5)).isoformat()
        hasta = (self.hoy + datetime.timedelta(days=35)).isoformat()
        datos = {
            "contrato": str(self.c1.pk),
            "id_tdr": "TDR-C1-EDITADO",
            "requerimientos": "Requerimientos actualizados.",
            "formatos": "PDF y Excel",
            "frecuencia_reportes": "Mensual",
            "penalidades": "2 %",
            "responsable": str(self.j1.pk),
            "documentos_disponibles": "Contrato",
            "documentos_faltantes": "Ninguno",
            "formato_esperado": "PDF",
            "fecha_limite": "",
            "estado_documental": "EN_CURSO",
            "item_nombre": ["Reporte editado"],
            "item_plantilla": [str(self.plantilla.pk)],
            "item_frecuencia": ["MENSUAL"],
            "item_primera_fecha": [primera],
            "item_hasta": [hasta],
            "item_junior": [str(self.j1.pk)],
            "item_senior": [""],
            f"item_dato_{self.plantilla.pk}_c_periodo": ["2027-01"],
            f"item_dato_{self.plantilla.pk}_c_nivel": ["3"],
            "accion": "vista_previa",
        }
        r = self.client.post(reverse("ficha_detalle", args=[self.ficha_c1.pk]), datos)
        self.assertEqual(r.status_code, 200)
        self.ficha_c1.refresh_from_db()
        self.assertEqual(self.ficha_c1.id_tdr, "TDR-C1-EDITADO")
        self.assertEqual(self.ficha_c1.nombre_archivo_tdr, "tdr_contrato.pdf")
        self.assertIsNotNone(r.context["vista_previa"])

    def test_respuesta_parcial_htmx_y_estructura_de_las_pantallas(self):
        self.client.force_login(self.gerente)
        r_htmx = self.client.get(reverse("fichas"), {"estado": "BORRADOR"}, HTTP_HX_REQUEST="true")
        self.assertEqual(r_htmx.status_code, 200)
        self.assertIn('id="resumen-filtros" hx-swap-oob="true"', r_htmx.content.decode())

        for url in (
            reverse("fichas"),
            reverse("ficha_nueva"),
            reverse("ficha_detalle", args=[self.ficha_c1.pk]),
        ):
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 200)
                self.assertIn("no-store", r["Cache-Control"])
                html = r.content.decode()
                self.assertEqual(html.count("<h1"), 1)
                self.assertNotRegex(html, r"<script>[^<]")

