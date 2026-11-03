"""Pruebas del buscador global y rendimiento (SDD del Sprint 2, hito S2-H10 · RF-36: HU-21 y RNF-12; caso 26 de la §13)."""
import datetime
import importlib
import os
import time
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.urls import reverse

import certitrack.settings as conf_modulo
from apps.busqueda.servicios import buscar
from apps.clientes.models import Cliente, Contrato, LineaServicio
from apps.entregables.models import Adjunto, Entregable, generar_codigo
from apps.entregables.tests import Base
from apps.entregables.tipos import TipoAdjunto
from apps.repositorio.models import DocumentoRepositorio

E = Entregable.Estado


class ConfiguracionBuscadorTests(Base):
    def test_buscador_limite_por_defecto_y_en_env_example(self):
        self.assertEqual(settings.BUSCADOR_LIMITE, 20)
        env_example = (Path(settings.BASE_DIR) / ".env.example").read_text(encoding="utf-8")
        self.assertIn("BUSCADOR_LIMITE=20", env_example)

    def test_buscador_limite_invalido_lanza_improperly_configured(self):
        for valor in ("0", "-5", "abc"):
            with self.subTest(valor=valor):
                with patch.dict(os.environ, {"BUSCADOR_LIMITE": valor}):
                    with self.assertRaises(ImproperlyConfigured):
                        importlib.reload(conf_modulo)
        importlib.reload(conf_modulo)


class Caso26BuscadorYVisibilidadTests(Base):
    """Caso 26 (§13): el buscador nunca devuelve resultados fuera de la visibilidad y responde en menos de 2 s."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.linea = LineaServicio.objects.get(nombre="Digitalización")
        cls.cliente_andino = Cliente.objects.create(nombre="Banco Andino Ficticio", sector="BANCA")
        cls.cliente_secreto = Cliente.objects.create(nombre="Corporación Pacífico Secreta", sector="TELECOM")

        cls.c_andino = Contrato.objects.create(
            cliente=cls.cliente_andino,
            numero_contrato="DEMO-2026-001",
            descripcion="Servicio de digitalización documental",
            linea_servicio=cls.linea,
            fecha_inicio="2026-01-01",
            fecha_fin="2026-12-31",
            senior_responsable=cls.s1,
        )
        cls.c_andino.juniors.add(cls.j1)

        cls.c_secreto = Contrato.objects.create(
            cliente=cls.cliente_secreto,
            numero_contrato="SEC-2026-099",
            descripcion="Custodia confidencial Pacífico",
            linea_servicio=cls.linea,
            fecha_inicio="2026-01-01",
            fecha_fin="2026-12-31",
            senior_responsable=cls.s2,
        )
        cls.c_secreto.juniors.add(cls.j2)

        # Entregable visible para j1 y s1 (con tilde en el título)
        cls.e_andino = Entregable.objects.create(
            contrato=cls.c_andino,
            plantilla=cls.plantilla,
            titulo="Informe técnico 03",
            id_tdr="TDR-ANDINO-03",
            fecha_recepcion=datetime.date(2026, 10, 1),
            plazo=datetime.date(2026, 10, 20),
            datos={"c_resumen": "ok"},
            estado=E.EN_PROCESO,
            junior_asignado=cls.j1,
            senior_revisor=cls.s1,
            creado_por=cls.s1,
        )
        cls.adj_andino = Adjunto.objects.create(
            entregable=cls.e_andino,
            archivo="demo/tdr_banco_andino.pdf",
            nombre_original="tdr_banco_andino.pdf",
            tipo=TipoAdjunto.TDR,
            version=2,
            comentario="TDR firmado por Banco Andino",
            subido_por=cls.j1,
        )
        cls.doc_andino = DocumentoRepositorio.objects.create(
            titulo="Formato de reporte mensual Andino",
            categoria=DocumentoRepositorio.Categoria.PLANTILLA_CLIENTE,
            cliente=cls.cliente_andino,
            tipo_documento=DocumentoRepositorio.TipoDocumento.REPORTE,
            linea_servicio=cls.linea,
            creado_por=cls.s1,
        )

        # Entregable, adjunto y plantilla de cliente ajenos a j1 y s1 (solo visibles para j2, s2, gerente y admin)
        cls.e_secreto = Entregable.objects.create(
            contrato=cls.c_secreto,
            plantilla=cls.plantilla,
            titulo="Informe técnico Pacífico confidencial",
            id_tdr="TDR-PACIFICO-99",
            fecha_recepcion=datetime.date(2026, 10, 1),
            plazo=datetime.date(2026, 11, 15),
            datos={"c_resumen": "ok"},
            estado=E.LISTO_PARA_ENTREGA,
            junior_asignado=cls.j2,
            senior_revisor=cls.s2,
            creado_por=cls.s2,
        )
        cls.adj_secreto = Adjunto.objects.create(
            entregable=cls.e_secreto,
            archivo="demo/anexo_pacifico.pdf",
            nombre_original="anexo_pacifico.pdf",
            tipo=TipoAdjunto.EVIDENCIA,
            version=1,
            comentario="Evidencia confidencial Pacífico",
            subido_por=cls.j2,
        )
        cls.doc_secreto = DocumentoRepositorio.objects.create(
            titulo="Plantilla exclusiva Pacífico",
            categoria=DocumentoRepositorio.Categoria.PLANTILLA_CLIENTE,
            cliente=cls.cliente_secreto,
            tipo_documento=DocumentoRepositorio.TipoDocumento.CARTA,
            linea_servicio=cls.linea,
            creado_por=cls.s2,
        )

    def test_caso_26_un_junior_nunca_encuentra_nada_fuera_de_su_visibilidad(self):
        # j1 busca «Pacífico» (sin tilde: «pacifico»): 0 resultados en los 5 grupos
        res_j1 = buscar(self.j1, {"q": "pacifico"})
        self.assertEqual(res_j1["total_resultados"], 0)
        for grupo in ("entregables", "contratos", "clientes", "adjuntos", "repositorio"):
            self.assertEqual(res_j1[grupo], [], grupo)

        # j1 busca «tecnico»: solo encuentra su propio entregable «Informe técnico 03», nunca el de Pacífico
        res_tec_j1 = buscar(self.j1, {"q": "tecnico"})
        self.assertEqual([e.pk for e in res_tec_j1["entregables"]], [self.e_andino.pk])

        # Gerente busca «pacifico»: encuentra los 5 grupos de Pacífico
        res_ger = buscar(self.gerente, {"q": "pacifico"})
        self.assertEqual([e.pk for e in res_ger["entregables"]], [self.e_secreto.pk])
        self.assertEqual([c.pk for c in res_ger["contratos"]], [self.c_secreto.pk])
        self.assertEqual([cl.pk for cl in res_ger["clientes"]], [self.cliente_secreto.pk])
        self.assertEqual([a.pk for a in res_ger["adjuntos"]], [self.adj_secreto.pk])
        self.assertEqual([d.pk for d in res_ger["repositorio"]], [self.doc_secreto.pk])

    def test_busqueda_insensible_a_mayusculas_y_tildes_en_todos_los_campos(self):
        # Sin tilde («tecnico») y en mayúsculas («TECNICO») encuentran «Informe técnico 03»
        for termino in ("tecnico", "técnico", "TECNICO", "TÉCNICO", self.e_andino.codigo, "TDR-ANDINO-03"):
            with self.subTest(termino=termino):
                res = buscar(self.j1, {"q": termino})
                self.assertIn(self.e_andino, res["entregables"])

        # Búsqueda de «ANDINO» para j1 devuelve resultados en los 5 grupos
        res_andino = buscar(self.j1, {"q": "ANDINO"})
        self.assertIn(self.e_andino, res_andino["entregables"])
        self.assertIn(self.c_andino, res_andino["contratos"])
        self.assertIn(self.cliente_andino, res_andino["clientes"])
        self.assertIn(self.adj_andino, res_andino["adjuntos"])
        self.assertIn(self.doc_andino, res_andino["repositorio"])

    def test_regla_de_minimo_dos_caracteres(self):
        for q in ("", " ", "a", "  z  "):
            with self.subTest(q=repr(q)):
                res = buscar(self.gerente, {"q": q})
                self.assertFalse(res["busqueda_activa"])
                self.assertEqual(res["total_resultados"], 0)

    def test_filtros_acotan_y_nunca_amplian_la_visibilidad_ni_fallan_con_datos_invalidos(self):
        # Filtro por estado: e_andino está EN_PROCESO y e_secreto en LISTO_PARA_ENTREGA
        res_en_proc = buscar(self.gerente, {"q": "tecnico", "estado": E.EN_PROCESO})
        self.assertEqual([e.pk for e in res_en_proc["entregables"]], [self.e_andino.pk])

        # Filtro por tipo_documento: TDR acota adjuntos a tdr_banco_andino.pdf y descarta el REPORTE del repositorio
        res_tdr = buscar(self.j1, {"q": "andino", "tipo_documento": "TDR"})
        self.assertEqual([a.pk for a in res_tdr["adjuntos"]], [self.adj_andino.pk])
        self.assertEqual(res_tdr["repositorio"], [])

        # Filtro por fechas (desde / hasta sobre el plazo)
        res_oct = buscar(self.gerente, {"q": "tecnico", "desde": "2026-10-01", "hasta": "2026-10-31"})
        self.assertEqual([e.pk for e in res_oct["entregables"]], [self.e_andino.pk])

        # j1 filtra por el cliente ajeno: sigue viendo 0 resultados
        res_ajeno = buscar(self.j1, {"q": "informe", "cliente": self.cliente_secreto.pk})
        self.assertEqual(res_ajeno["total_resultados"], 0)

        # Valores inválidos o fuera de rango se ignoran sin error 500
        self.client.force_login(self.j1)
        r = self.client.get(
            reverse("buscar"),
            {
                "q": "andino",
                "desde": "fecha-mala",
                "hasta": "2026-99-99",
                "cliente": str(2**63),
                "estado": "INVENTADO",
                "tipo_documento": "INVENTADO",
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["filtros_activos"], {})

    def test_vista_completa_fragmento_htmx_y_caja_en_barra_superior(self):
        self.assertEqual(self.client.get(reverse("buscar")).status_code, 302)
        self.client.force_login(self.j1)

        # La caja de búsqueda aparece en la barra superior de las pantallas privadas
        r_inicio = self.client.get(reverse("inicio"))
        self.assertContains(r_inicio, f'action="{reverse("buscar")}"')
        self.assertContains(r_inicio, 'name="q"')

        # Página completa /buscar/?q=andino
        r_full = self.client.get(reverse("buscar"), {"q": "andino"})
        self.assertEqual(r_full.status_code, 200)
        self.assertContains(r_full, "Resultados para «andino»")
        self.assertContains(r_full, self.e_andino.codigo)

        # Petición HTMX devuelve solo el fragmento de resultados
        r_htmx = self.client.get(reverse("buscar"), {"q": "andino"}, HTTP_HX_REQUEST="true")
        self.assertEqual(r_htmx.status_code, 200)
        self.assertNotContains(r_htmx, '<header class="barra">')
        self.assertContains(r_htmx, self.e_andino.codigo)

    @override_settings(BUSCADOR_LIMITE=20)
    def test_rnf_12_rendimiento_menos_de_2_segundos_con_10_veces_el_volumen_del_seed(self):
        # Volumen del seed_demo multiplicado por 10 (~300 entregables, 300 adjuntos, 40 contratos, 80 docs del repositorio)
        ahora = datetime.datetime.now(datetime.timezone.utc)
        contratos_nuevos = [
            Contrato(
                cliente=self.cliente_andino if i % 2 == 0 else self.cliente_secreto,
                numero_contrato=f"PERF-2026-{i:03d}",
                descripcion=f"Contrato de prueba de rendimiento {i}",
                linea_servicio=self.linea,
                fecha_inicio=datetime.date(2026, 1, 1),
                fecha_fin=datetime.date(2026, 12, 31),
                senior_responsable=self.s1 if i % 2 == 0 else self.s2,
            )
            for i in range(40)
        ]
        Contrato.objects.bulk_create(contratos_nuevos)

        entregables_lote = [
            Entregable(
                contrato=self.c_andino if i % 2 == 0 else self.c_secreto,
                plantilla=self.plantilla,
                titulo=f"Informe técnico masivo {i:04d} para Banco Andino",
                id_tdr=f"TDR-MASIVO-{i:04d}",
                fecha_recepcion=datetime.date(2026, 10, 1),
                plazo=datetime.date(2026, 10, 1) + datetime.timedelta(days=i % 25),
                datos={"c_resumen": "ok"},
                estado=E.EN_PROCESO,
                junior_asignado=self.j1 if i % 2 == 0 else self.j2,
                senior_revisor=self.s1 if i % 2 == 0 else self.s2,
                creado_por=self.s1,
            )
            for i in range(300)
        ]
        creados = Entregable.objects.bulk_create(entregables_lote)
        for ent in creados:
            ent.codigo = generar_codigo(ent.pk, ahora)
        Entregable.objects.bulk_update(creados, ["codigo"])

        Adjunto.objects.bulk_create(
            [
                Adjunto(
                    entregable=ent,
                    archivo=f"demo/archivo_{idx}.pdf",
                    nombre_original=f"reporte_tecnico_andino_{idx:04d}.pdf",
                    tipo=TipoAdjunto.BORRADOR,
                    version=1,
                    comentario="Borrador técnico de revisión",
                    subido_por=self.j1,
                )
                for idx, ent in enumerate(creados)
            ]
        )

        DocumentoRepositorio.objects.bulk_create(
            [
                DocumentoRepositorio(
                    titulo=f"Formato técnico corporativo Andino {i:03d}",
                    categoria=DocumentoRepositorio.Categoria.PLANTILLA_CLIENTE,
                    cliente=self.cliente_andino,
                    tipo_documento=DocumentoRepositorio.TipoDocumento.REPORTE,
                    linea_servicio=self.linea,
                    creado_por=self.s1,
                )
                for i in range(80)
            ]
        )

        self.client.force_login(self.gerente)
        t0 = time.perf_counter()
        r = self.client.get(reverse("buscar"), {"q": "tecnico"})
        duracion = time.perf_counter() - t0

        self.assertEqual(r.status_code, 200)
        self.assertLess(duracion, 2.0, f"El buscador tardó {duracion:.3f} s (máximo RNF-12: 2,0 s)")
        self.assertEqual(len(r.context["entregables"]), 20)
        self.assertGreaterEqual(r.context["entregables_total"], 300)
        self.assertEqual(len(r.context["adjuntos"]), 20)
        self.assertEqual(len(r.context["repositorio"]), 20)
