"""SDD del Sprint 3, hito S3-H9: extracción de datos con OCR local (RF-48, HU-24).

Criterio de aceptación: «Con un motor simulado prellena y marca lo ilegible; sin Tesseract avisa y permite seguir a mano; nada se
guarda sin confirmar». Ninguna prueba exige Tesseract instalado: el motor se simula (ver testing.py).

  1. Prellenado con el texto del PDF y con el motor simulado       -> TextoDelPdfTests, OcrSimuladoTests
  2. Lo ilegible y lo no encontrado se marcan                      -> OcrSimuladoTests
  3. Sin Tesseract avisa y se sigue a mano                         -> SinOcrTests
  4. Nada se guarda sin confirmar                                  -> NadaSeGuardaSinConfirmarTests
  5. Extracción sobre un entregable (plantilla) y permisos         -> SobreUnEntregableTests, PermisosTests
"""
import datetime
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from apps.entregables import adjuntos
from apps.entregables.models import Adjunto, Entregable, HistorialEstado
from apps.entregables.tests import Base
from apps.entregables.tipos import TipoAdjunto

from . import campos, motores, servicios
from .models import Extraccion
from .testing import imagen_png, ocr_simulado, pdf_con_paginas, sin_ocr

E = Entregable.Estado


class ExtraccionBase(Base):
    def setUp(self):
        self.recibido = self.hoy - datetime.timedelta(days=3)
        self.plazo = self.hoy + datetime.timedelta(days=12)

    def lineas(self, contrato="C1", extra=()):
        return [
            "Cliente: Cliente Demo", f"Contrato: {contrato}", "ID-TDR: TDR-BAF-014",
            f"Recibido el: {self.recibido:%d/%m/%Y}", f"Plazo de entrega: {self.plazo:%d/%m/%Y}",
            "Periodo: Octubre 2026", "Nivel: 3", *extra,
        ]

    def pdf(self, *paginas, nombre="tdr.pdf"):
        return pdf_con_paginas(*(paginas or (self.lineas(),)), nombre=nombre)

    def campo(self, extraccion, clave):
        return next(c for c in extraccion.campos if c["clave"] == clave)

    def entrar(self, usuario):
        self.client.force_login(usuario)
        return self.client

    def subir(self, usuario, archivo=None, plantilla=None, **extra):
        """POST a «extraccion_nueva» (documento subido en «Nuevo entregable»)."""
        return self.entrar(usuario).post(reverse("extraccion_nueva"), {
            "archivo": archivo or self.pdf(), "plantilla": (plantilla or self.plantilla).pk, **extra,
        })


class TextoDelPdfTests(ExtraccionBase):
    def test_prellena_los_campos_con_el_texto_del_pdf(self):
        x = servicios.extraer(self.s1, self.pdf(), self.plantilla)
        self.assertEqual(x.motor, Extraccion.Motor.TEXTO_PDF)
        self.assertFalse(x.ilegible)
        self.assertEqual(self.campo(x, "contrato")["valor"], str(self.c1.pk))
        self.assertEqual(self.campo(x, "cliente")["valor"], "Cliente Demo")
        self.assertEqual(self.campo(x, "id_tdr")["valor"], "TDR-BAF-014")
        self.assertEqual(self.campo(x, "fecha_recepcion")["valor"], self.recibido.isoformat())
        self.assertEqual(self.campo(x, "plazo")["valor"], self.plazo.isoformat())
        self.assertEqual(self.campo(x, "campo:c_periodo")["valor"], "Octubre 2026")
        self.assertEqual(self.campo(x, "campo:c_nivel")["valor"], "3")
        for c in x.campos:  # cada campo trae su origen y su confianza
            self.assertEqual((c["estado"], c["confianza"]), ("ok", 100))
            self.assertIn("Página 1", c["origen"])

    def test_un_contrato_que_el_usuario_no_puede_elegir_no_se_propone(self):
        x = servicios.extraer(self.s1, self.pdf(self.lineas(contrato="C2")), self.plantilla)  # C2 es del senior s2
        contrato = self.campo(x, "contrato")
        self.assertEqual((contrato["valor"], contrato["estado"]), ("", "no_encontrado"))
        self.assertIn("completar a mano", contrato["origen"])

    def test_el_contrato_se_reconoce_sin_etiqueta_y_da_el_cliente(self):
        x = servicios.extraer(self.s1, self.pdf(["Solicitud de informe", "Referencia del contrato C1 vigente"]), self.plantilla)
        self.assertEqual(self.campo(x, "contrato")["valor"], str(self.c1.pk))
        self.assertEqual(self.campo(x, "cliente")["valor"], "Cliente Demo")

    def test_fechas_en_varios_formatos(self):
        casos = {
            "05/11/2026": datetime.date(2026, 11, 5), "5-11-2026": datetime.date(2026, 11, 5),
            "2026-11-05": datetime.date(2026, 11, 5), "5 de noviembre de 2026": datetime.date(2026, 11, 5),
            "5 de Setiembre del 2026": datetime.date(2026, 9, 5), "31/02/2026": None, "sin fecha": None,
        }
        for texto, esperada in casos.items():
            self.assertEqual(campos.parsear_fecha(texto), esperada, texto)

    def test_valores_de_plantilla_se_leen_segun_su_tipo(self):
        self.assertEqual(campos._numero("S/ 1.250,50 soles"), "1250.5")
        self.assertEqual(campos._numero("12"), "12")
        self.assertIsNone(campos._numero("sin número"))
        x = servicios.extraer(self.s1, self.pdf(self.lineas()[:6] + ["Nivel: alto"]), self.plantilla)
        nivel = self.campo(x, "campo:c_nivel")
        self.assertEqual((nivel["valor"], nivel["estado"]), ("", "no_encontrado"))
        self.assertIn("No se pudo leer un valor válido", nivel["origen"])

    def test_un_archivo_que_no_es_pdf_ni_imagen_se_rechaza(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            servicios.extraer(self.s1, SimpleUploadedFile("notas.txt", b"Cliente: Cliente Demo"), self.plantilla)
        with self.assertRaises(ValidationError) as cm:
            servicios.extraer(self.s1, SimpleUploadedFile("falso.pdf", b"esto no es un pdf"), self.plantilla)
        self.assertIn("No se pudo leer el PDF", cm.exception.messages[0])
        self.assertEqual(Extraccion.objects.count(), 0)

    @override_settings(OCR_MAX_PAGINAS=2)
    def test_solo_se_leen_las_paginas_del_limite(self):
        x = servicios.extraer(self.s1, self.pdf(["Cliente: Cliente Demo"], ["Plazo: 01/12/2026"], ["Periodo: Tercera"]), self.plantilla)
        self.assertTrue(any("solo se leyeron las primeras 2" in a for a in x.avisos))
        self.assertNotIn("Tercera", x.texto)


class OcrSimuladoTests(ExtraccionBase):
    def test_prellena_y_marca_lo_ilegible(self):
        """Página 1 con texto; página 2 escaneada y leída con el motor simulado, con una línea de confianza baja."""
        escaneada = [("Nivel: 3", 41), ("Periodo: Octubre 2026", 79)]
        with ocr_simulado(escaneada) as ocr:
            x = servicios.extraer(self.s1, self.pdf(self.lineas()[:5], []), self.plantilla)
        self.assertEqual(ocr.call_count, 1)  # solo la página sin texto pasa por OCR
        self.assertEqual(x.motor, Extraccion.Motor.TESSERACT)
        self.assertEqual(self.campo(x, "contrato")["valor"], str(self.c1.pk))  # lo del texto sigue prellenado
        periodo = self.campo(x, "campo:c_periodo")
        self.assertEqual((periodo["valor"], periodo["estado"], periodo["confianza"]), ("Octubre 2026", "ok", 79))
        self.assertIn("Página 2", periodo["origen"])
        nivel = self.campo(x, "campo:c_nivel")  # confianza 41 < 60: se propone, pero resaltado
        self.assertEqual((nivel["valor"], nivel["estado"], nivel["confianza"]), ("3", "poco_legible", 41))
        self.assertIn("Texto poco legible (página 2)", nivel["origen"])
        self.assertTrue(x.ilegible)

    def test_aviso_si_la_confianza_media_del_ocr_es_baja(self):
        with ocr_simulado([("Cliente: Cliente Demo", 50), ("Plazo: 01/12/2026", 56)]):
            x = servicios.extraer(self.s1, imagen_png(), self.plantilla)
        self.assertEqual(x.motor, Extraccion.Motor.TESSERACT)
        self.assertTrue(x.ilegible)
        self.assertIn("la confianza media del OCR es 53 (mínimo 60)", x.avisos[0])

    def test_lo_que_no_se_encuentra_queda_vacio_y_resaltado(self):
        with ocr_simulado([("Cliente: Cliente Demo", 90), ("Contrato: C1", 88)]):
            x = servicios.extraer(self.s1, imagen_png(), self.plantilla)
        self.assertFalse(x.ilegible)  # se leyó bien; solo faltan datos
        plazo = self.campo(x, "plazo")
        self.assertEqual((plazo["valor"], plazo["estado"], plazo["confianza"]), ("", "no_encontrado", None))
        self.assertEqual(plazo["origen"], "No encontrado: completar a mano")
        self.assertTrue(any(a.startswith("No se encontró:") and "Plazo" in a for a in x.avisos))
        respuesta = self.entrar(self.s1).get(reverse("extraccion_vista", args=[x.pk]))
        self.assertContains(respuesta, "extr-dudoso")
        self.assertContains(respuesta, "No encontrado: completar a mano")

    def test_una_pagina_que_no_da_texto_se_avisa(self):
        with ocr_simulado([]):
            x = servicios.extraer(self.s1, imagen_png(), self.plantilla)
        self.assertEqual(x.motor, Extraccion.Motor.NINGUNO)
        self.assertTrue(x.ilegible)
        self.assertTrue(any("La página 1 no dio texto" in a for a in x.avisos))

    def test_el_ocr_que_falla_no_tumba_la_extraccion(self):
        from unittest import mock

        with mock.patch.object(motores, "tesseract_disponible", return_value=True), \
                mock.patch.object(motores, "ocr_imagen", side_effect=motores.ErrorOCR("falta el idioma spa")):
            x = servicios.extraer(self.s1, imagen_png(), self.plantilla)
        self.assertTrue(any("falta el idioma spa" in a for a in x.avisos))
        self.assertTrue(x.ilegible)

    def test_el_tsv_de_tesseract_se_agrupa_por_linea(self):
        tsv = "\t".join("level page_num block_num par_num line_num word_num left top width height conf text".split()) + "\n"
        filas = [
            ("5", "1", "1", "1", "1", "1", "0", "0", "9", "9", "90", "Plazo:"),
            ("5", "1", "1", "1", "1", "2", "0", "0", "9", "9", "70", "01/12/2026"),
            ("5", "1", "1", "1", "2", "1", "0", "0", "9", "9", "-1", "ruido"),
            ("5", "1", "1", "1", "3", "1", "0", "0", "9", "9", "85", "Nivel:"),
            ("4", "1", "1", "1", "3", "0", "0", "0", "9", "9", "-1", ""),
        ]
        tsv += "\n".join("\t".join(f) for f in filas)
        self.assertEqual(motores._lineas_de_tsv(tsv), [("Plazo: 01/12/2026", 80), ("Nivel:", 85)])

    @override_settings(TESSERACT_CMD="programa-que-no-existe-certitrack")
    def test_sin_el_programa_tesseract_no_esta_disponible(self):
        self.assertFalse(motores.tesseract_disponible())


class SinOcrTests(ExtraccionBase):
    def test_pdf_escaneado_sin_tesseract_avisa_y_deja_seguir_a_mano(self):
        with sin_ocr() as ocr:
            x = servicios.extraer(self.s1, self.pdf(self.lineas()[:3], []), self.plantilla)
        ocr.assert_not_called()
        self.assertTrue(x.avisos[0].startswith(motores.AVISO_SIN_OCR))
        self.assertIn("página 2", x.avisos[0])
        self.assertEqual(x.motor, Extraccion.Motor.TEXTO_PDF)  # lo que traía texto se leyó igual
        self.assertEqual(self.campo(x, "contrato")["valor"], str(self.c1.pk))
        self.assertTrue(x.ilegible)

    def test_imagen_sin_tesseract_da_la_vista_previa_vacia_y_se_completa_a_mano(self):
        with sin_ocr():
            respuesta = self.subir(self.s1, imagen_png(), follow=False)
        x = Extraccion.objects.get()
        self.assertRedirects(respuesta, reverse("extraccion_vista", args=[x.pk]))
        self.assertEqual(x.motor, Extraccion.Motor.NINGUNO)
        self.assertTrue(all(c["estado"] == "no_encontrado" for c in x.campos))
        with sin_ocr():
            pagina = self.client.get(respuesta.url)
        self.assertContains(pagina, "El OCR no está disponible en este servidor.")
        self.assertContains(pagina, "no disponible en este servidor")
        # Se sigue a mano: la persona escribe los valores en la vista previa, aplica y crea el entregable.
        valores = {f"valor-{i}": v for i, v in enumerate(["", str(self.c1.pk), "TDR-MANUAL", self.recibido.isoformat(),
                                                           self.plazo.isoformat(), "Octubre", "4"])}
        aplicada = self.client.post(respuesta.url, {"accion": "aplicar", **valores})
        self.assertEqual(aplicada.status_code, 302)
        creada = self.client.post(reverse("entregable_nuevo"), self.datos_de_creacion(x, id_tdr="TDR-MANUAL"))
        self.assertEqual(creada.status_code, 302)
        self.assertTrue(Entregable.objects.filter(id_tdr="TDR-MANUAL").exists())

    def datos_de_creacion(self, extraccion, **cambios):
        return {
            "plantilla": self.plantilla.pk, "extraccion": extraccion.pk, "contrato": self.c1.pk, "titulo": "Informe",
            "id_tdr": "TDR-1", "fecha_recepcion": self.recibido.isoformat(), "plazo": self.plazo.isoformat(),
            "c_periodo": "Octubre", "c_nivel": "4", "junior_asignado": self.j1.pk, **cambios,
        }

    def test_la_pantalla_de_nuevo_entregable_muestra_el_estado_de_los_motores(self):
        with sin_ocr():
            pagina = self.entrar(self.s1).get(reverse("entregable_nuevo"), {"plantilla": self.plantilla.pk})
        self.assertContains(pagina, "Prellenar desde un documento")
        self.assertContains(pagina, "no disponible en este servidor")
        with ocr_simulado():
            pagina = self.client.get(reverse("entregable_nuevo"), {"plantilla": self.plantilla.pk})
        self.assertContains(pagina, "«OCR Tesseract» (sí)")


class NadaSeGuardaSinConfirmarTests(ExtraccionBase):
    def conteos(self):
        return (Entregable.objects.count(), Adjunto.objects.count(), HistorialEstado.objects.count())

    def test_extraer_y_ver_la_vista_previa_no_crea_ni_cambia_nada(self):
        antes = self.conteos()
        datos_e1 = dict(self.e1.datos)
        respuesta = self.subir(self.s1)
        x = Extraccion.objects.get()
        self.assertEqual(self.client.get(respuesta.url).status_code, 200)
        self.assertEqual(self.conteos(), antes)
        self.assertIsNone(x.aplicada_en)
        self.assertIsNone(x.entregable)
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.datos, datos_e1)

    def test_descartar_borra_la_propuesta_y_su_archivo(self):
        self.subir(self.s1)
        x = Extraccion.objects.get()
        ruta = x.archivo.path
        antes = self.conteos()
        self.client.post(reverse("extraccion_vista", args=[x.pk]), {"accion": "descartar"})
        self.assertFalse(Extraccion.objects.exists())
        self.assertEqual(self.conteos(), antes)
        import os

        self.assertFalse(os.path.exists(ruta))

    def test_aplicar_pasa_los_valores_editados_al_formulario_sin_crear_el_entregable(self):
        self.subir(self.s1)
        x = Extraccion.objects.get()
        valores = {f"valor-{i}": c["valor"] for i, c in enumerate(x.campos)}
        valores["valor-2"] = "TDR-EDITADO"  # la persona corrige el ID-TDR
        antes = self.conteos()
        aplicada = self.client.post(reverse("extraccion_vista", args=[x.pk]), {"accion": "aplicar", **valores})
        self.assertRedirects(aplicada, f"{reverse('entregable_nuevo')}?plantilla={self.plantilla.pk}&extraccion={x.pk}",
                             fetch_redirect_response=False)
        self.assertEqual(self.conteos(), antes)  # todavía no existe el entregable
        x.refresh_from_db()
        self.assertIsNotNone(x.aplicada_en)
        pagina = self.client.get(aplicada.url)
        form = pagina.context["form"]
        self.assertEqual(form["id_tdr"].value(), "TDR-EDITADO")
        self.assertEqual(form["contrato"].value(), self.c1.pk)
        self.assertEqual(form["plazo"].value(), self.plazo)
        self.assertEqual(form["c_periodo"].value(), "Octubre 2026")
        self.assertContains(pagina, "Datos prellenados desde")
        self.assertEqual(self.conteos(), antes)

    def test_al_crear_se_validan_los_valores_y_el_documento_se_adjunta_como_tdr(self):
        self.subir(self.s1)
        x = Extraccion.objects.get()
        valores = {f"valor-{i}": c["valor"] for i, c in enumerate(x.campos)}
        self.client.post(reverse("extraccion_vista", args=[x.pk]), {"accion": "aplicar", **valores})
        datos = {
            "plantilla": self.plantilla.pk, "extraccion": x.pk, "contrato": self.c1.pk, "titulo": "Informe",
            "id_tdr": "TDR-BAF-014", "fecha_recepcion": self.recibido.isoformat(), "plazo": self.plazo.isoformat(),
            "c_periodo": "Octubre 2026", "c_nivel": "3", "junior_asignado": self.j1.pk,
        }
        # El Poka-Yoke de siempre: un plazo vencido se rechaza aunque venga de la extracción, y no se adjunta nada.
        antes = self.conteos()
        rechazada = self.client.post(reverse("entregable_nuevo"), {**datos, "plazo": (self.hoy - datetime.timedelta(days=1)).isoformat()})
        self.assertEqual(rechazada.status_code, 200)
        self.assertContains(rechazada, "El plazo no puede ser anterior a hoy.")
        self.assertContains(rechazada, f'name="extraccion" value="{x.pk}"')
        self.assertEqual(self.conteos(), antes)
        creada = self.client.post(reverse("entregable_nuevo"), datos)
        self.assertEqual(creada.status_code, 302)
        e = Entregable.objects.get(titulo="Informe")
        adjunto = e.adjuntos.get()
        self.assertEqual((adjunto.tipo, adjunto.nombre_original), (TipoAdjunto.TDR, "tdr.pdf"))
        x.refresh_from_db()
        self.assertEqual(x.entregable, e)
        # Una extracción ya usada no vuelve a prellenar ni a adjuntarse.
        self.assertIsNone(servicios.pendiente_para_crear(self.s1, x.pk))

    def test_una_extraccion_sin_aplicar_no_prellena_el_formulario(self):
        self.subir(self.s1)
        x = Extraccion.objects.get()
        pagina = self.client.get(reverse("entregable_nuevo"), {"plantilla": self.plantilla.pk, "extraccion": x.pk})
        self.assertNotContains(pagina, "Datos prellenados desde")
        self.assertNotEqual(pagina.context["form"]["id_tdr"].value(), "TDR-BAF-014")

    def test_el_documento_con_error_no_deja_extraccion_ni_nada(self):
        antes = self.conteos()
        respuesta = self.subir(self.s1, SimpleUploadedFile("notas.txt", b"hola"))
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Extraccion.objects.count(), 0)
        self.assertEqual(self.conteos(), antes)
        sin_archivo = self.entrar(self.s1).post(reverse("extraccion_nueva"), {"plantilla": self.plantilla.pk})
        self.assertEqual(sin_archivo.status_code, 302)
        self.assertEqual(Extraccion.objects.count(), 0)


class SobreUnEntregableTests(ExtraccionBase):
    def setUp(self):
        super().setUp()
        self.e1.datos = {"c_periodo": "", "c_nivel": ""}
        self.e1.save(update_fields=["datos"])
        self.adjunto = adjuntos.crear_adjunto(self.e1, self.s1, self.pdf(), TipoAdjunto.TDR, "TDR del cliente")

    def extraer(self, usuario, entregable=None, adjunto=None):
        return self.entrar(usuario).post(reverse("extraccion_nueva"), {
            "entregable": (entregable or self.e1).pk, "adjunto": (adjunto or self.adjunto).pk,
        })

    def test_el_detalle_ofrece_extraer_datos_a_quien_puede(self):
        for usuario in (self.j1, self.s1, self.gerente):
            pagina = self.entrar(usuario).get(reverse("entregable_detalle", args=[self.e1.pk]))
            self.assertContains(pagina, "Extraer datos de un documento")
        self.e1.estado = E.VERIFICACION_SENIOR
        self.e1.save()
        pagina = self.client.get(reverse("entregable_detalle", args=[self.e1.pk]))
        self.assertNotContains(pagina, "Extraer datos de un documento")

    def test_completa_los_datos_de_la_plantilla_solo_al_confirmar_y_deja_historial(self):
        respuesta = self.extraer(self.j1)
        x = Extraccion.objects.get()
        self.assertRedirects(respuesta, reverse("extraccion_vista", args=[x.pk]))
        self.assertEqual([c["clave"] for c in x.campos], ["campo:c_periodo", "campo:c_nivel"])  # solo la plantilla
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.datos, {"c_periodo": "", "c_nivel": ""})  # aún nada
        aplicada = self.client.post(respuesta.url, {"accion": "aplicar", "valor-0": "Octubre 2026", "valor-1": "3"})
        self.assertRedirects(aplicada, reverse("entregable_detalle", args=[self.e1.pk]) + "#extraer-datos", fetch_redirect_response=False)
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.datos, {"c_periodo": "Octubre 2026", "c_nivel": "3"})
        self.assertTrue(HistorialEstado.objects.filter(entregable=self.e1, detalle__contains="Completó datos de la plantilla").exists())
        x.refresh_from_db()
        self.assertIsNotNone(x.aplicada_en)

    def test_un_valor_invalido_no_guarda_nada(self):
        respuesta = self.extraer(self.j1)
        x = Extraccion.objects.get()
        malo = self.client.post(respuesta.url, {"accion": "aplicar", "valor-0": "Octubre 2026", "valor-1": "muchos"})
        self.assertEqual(malo.status_code, 200)
        self.assertContains(malo, "debe ser un número")
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.datos, {"c_periodo": "", "c_nivel": ""})  # ni siquiera el valor correcto
        x.refresh_from_db()
        self.assertIsNone(x.aplicada_en)

    def test_los_valores_vacios_no_borran_los_datos_existentes(self):
        self.e1.datos = {"c_periodo": "Setiembre", "c_nivel": "2"}
        self.e1.save(update_fields=["datos"])
        respuesta = self.extraer(self.j1)
        self.client.post(respuesta.url, {"accion": "aplicar", "valor-0": "", "valor-1": "5"})
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.datos, {"c_periodo": "Setiembre", "c_nivel": "5"})
        self.assertEqual(Decimal(self.e1.datos["c_nivel"]), 5)

    def test_no_se_puede_confirmar_si_el_entregable_ya_paso_de_en_proceso(self):
        respuesta = self.extraer(self.j1)
        self.e1.estado = E.VERIFICACION_SENIOR
        self.e1.save()
        confirmada = self.client.post(respuesta.url, {"accion": "aplicar", "valor-0": "X", "valor-1": "1"})
        self.assertEqual(confirmada.status_code, 403)
        self.e1.refresh_from_db()
        self.assertEqual(self.e1.datos["c_periodo"], "")

    def test_permisos_para_extraer_sobre_un_entregable(self):
        self.assertEqual(self.extraer(self.j2).status_code, 404)  # no lo ve
        self.assertEqual(self.extraer(self.s2).status_code, 404)
        self.e1.estado = E.LISTO_PARA_ENTREGA
        self.e1.save()
        self.assertEqual(self.extraer(self.j1).status_code, 403)  # fuera de Por hacer / En proceso
        self.assertFalse(Extraccion.objects.exists())

    def test_el_adjunto_debe_ser_del_entregable(self):
        otro = adjuntos.crear_adjunto(self.e2, self.s2, self.pdf(), TipoAdjunto.TDR, "otro")
        self.assertEqual(self.extraer(self.j1, adjunto=otro).status_code, 404)


class PermisosTests(ExtraccionBase):
    def test_hay_que_iniciar_sesion(self):
        for url in (reverse("extraccion_nueva"), reverse("extraccion_vista", args=[1])):
            self.assertEqual(self.client.get(url).status_code, 302)
            self.assertIn("login", self.client.get(url).url)

    def test_un_junior_no_extrae_en_nuevo_entregable(self):
        self.assertEqual(self.subir(self.j1).status_code, 403)
        self.assertFalse(Extraccion.objects.exists())

    def test_cada_usuario_ve_solo_sus_extracciones(self):
        self.subir(self.s1)
        x = Extraccion.objects.get()
        self.assertEqual(self.entrar(self.s2).get(reverse("extraccion_vista", args=[x.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("extraccion_vista", args=[x.pk]), {"accion": "descartar"}).status_code, 404)
        self.assertEqual(self.entrar(self.gerente).get(reverse("extraccion_vista", args=[x.pk])).status_code, 404)
        self.assertEqual(self.entrar(self.s1).get(reverse("extraccion_vista", args=[x.pk])).status_code, 200)
        self.assertEqual(list(servicios.propias(self.s2)), [])

    def test_la_extraccion_de_otro_no_prellena_el_formulario_de_nadie_mas(self):
        self.subir(self.s1)
        x = Extraccion.objects.get()
        x.aplicada_en = x.creada_en
        x.save()
        self.assertIsNone(servicios.pendiente_para_crear(self.s2, x.pk))
        self.assertIsNotNone(servicios.pendiente_para_crear(self.s1, x.pk))
        self.assertIsNone(servicios.pendiente_para_crear(self.s1, "no-es-un-numero"))

    def test_s1_no_puede_proponer_contratos_de_s2_aunque_el_documento_los_nombre(self):
        self.subir(self.s1, self.pdf(self.lineas(contrato="C2")))
        x = Extraccion.objects.get()
        self.assertEqual(self.campo(x, "contrato")["valor"], "")
        self.assertEqual(self.campo(x, "cliente")["valor"], "Cliente Demo")  # el cliente sí lo ve (por C1)
