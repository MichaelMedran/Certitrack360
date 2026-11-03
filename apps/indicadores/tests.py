"""Pruebas del panel de indicadores de desempeño (SDD del Sprint 2, hito S2-H8 · RF-33: HU-13; caso 24 de la §13)."""
import datetime

from django.urls import reverse
from django.utils import timezone

from apps.clientes.models import Cliente, Contrato, PlantillaTDR
from apps.entregables.models import (
    Adjunto,
    Entrega,
    Entregable,
    HistorialEstado,
    Observacion,
    RegistroTiempo,
    TipoError,
)
from apps.entregables.tests import Base
from apps.entregables.tipos import TipoAdjunto
from apps.indicadores.servicios import (
    FORMULA_A_TIEMPO,
    FORMULA_OBSERVACIONES,
    FORMULA_REPROCESO,
    FORMULA_TIEMPO,
    calcular_indicadores,
)

E = Entregable.Estado


class Caso24IndicadoresYVisibilidadTests(Base):
    """Caso 24 (§13): los indicadores coinciden con un conjunto de datos conocido y respetan la visibilidad por rol."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Limpiamos los entregables base para construir un conjunto de datos conocido con cifras exactas.
        Entregable.objects.all().delete()

        cls.cliente_b = Cliente.objects.create(nombre="Cliente B", sector="TELECOM")
        cls.c_otro = Contrato.objects.create(
            cliente=cls.cliente_b,
            numero_contrato="C-OTRO",
            fecha_inicio="2026-01-01",
            fecha_fin="2026-12-31",
            senior_responsable=cls.s2,
        )
        cls.c_otro.juniors.add(cls.j2)

        cls.plantilla_matriz = PlantillaTDR.objects.create(
            nombre="Matriz de riesgos",
            campos_requeridos=[{"nombre": "c_alcance", "etiqueta": "Alcance", "tipo": "texto"}],
        )

        # --- Contrato C1 (senior: s1, junior: j1, cliente: Cliente A) ---
        # 1) Entregado a tiempo con Entrega registrada (recepción 01/10, entrega 06/10, plazo 10/10 -> 5 días, a tiempo)
        cls.e_ok = Entregable.objects.create(
            contrato=cls.c1,
            plantilla=cls.plantilla,
            titulo="Informe Octubre OK",
            id_tdr="TDR-101",
            fecha_recepcion=datetime.date(2026, 10, 1),
            plazo=datetime.date(2026, 10, 10),
            datos={"c_resumen": "ok"},
            estado=E.HECHO,
            junior_asignado=cls.j1,
            senior_revisor=cls.s1,
            creado_por=cls.s1,
        )
        cls._registrar_entrega(cls.e_ok, cls.s1, datetime.date(2026, 10, 6))
        # Registro de tiempo cerrado: 4 horas
        cls._registrar_tiempo(cls.e_ok, cls.j1, datetime.datetime(2026, 10, 2, 9, 0), horas=4)

        # 2) Entregado fuera de plazo y con reproceso (recepción 01/10, entrega 15/10, plazo 10/10 -> 14 días, tarde)
        cls.e_tarde = Entregable.objects.create(
            contrato=cls.c1,
            plantilla=cls.plantilla,
            titulo="Informe Octubre Tarde",
            id_tdr="TDR-102",
            fecha_recepcion=datetime.date(2026, 10, 1),
            plazo=datetime.date(2026, 10, 10),
            datos={"c_resumen": "ok"},
            estado=E.HECHO,
            junior_asignado=cls.j1,
            senior_revisor=cls.s1,
            creado_por=cls.s1,
        )
        cls._registrar_entrega(cls.e_tarde, cls.s1, datetime.date(2026, 10, 15))
        HistorialEstado.objects.create(
            entregable=cls.e_tarde,
            estado_anterior=E.VERIFICACION_SENIOR,
            estado_nuevo=E.EN_PROCESO,
            usuario=cls.s1,
            detalle="Devuelto por formato",
        )
        cls._registrar_tiempo(cls.e_tarde, cls.j1, datetime.datetime(2026, 10, 3, 9, 0), horas=8)
        Observacion.objects.create(
            entregable=cls.e_tarde,
            autor=cls.s1,
            responsable=cls.j1,
            tipo_error=TipoError.FORMATO,
            descripcion="Falta portada",
        )
        Observacion.objects.create(
            entregable=cls.e_tarde,
            autor=cls.s1,
            responsable=cls.j1,
            tipo_error=TipoError.FORMATO,
            descripcion="Margen incorrecto",
        )

        # 3) Entregado cerrado antes del Sprint 2 (sin Entrega, usa HistorialEstado del paso a HECHO: 08/10 <= plazo 10/10)
        # Recepción 02/10, entrega por historial 08/10 -> 6 días, a tiempo
        cls.e_pre_s2 = Entregable.objects.create(
            contrato=cls.c1,
            plantilla=cls.plantilla_matriz,
            titulo="Matriz Pre-S2",
            id_tdr="TDR-103",
            fecha_recepcion=datetime.date(2026, 10, 2),
            plazo=datetime.date(2026, 10, 10),
            datos={"c_alcance": "total"},
            estado=E.HECHO,
            junior_asignado=cls.j1,
            senior_revisor=cls.s1,
            creado_por=cls.s1,
        )
        paso_hecho = HistorialEstado.objects.create(
            entregable=cls.e_pre_s2,
            estado_anterior=E.LISTO_PARA_ENTREGA,
            estado_nuevo=E.HECHO,
            usuario=cls.s1,
        )
        fecha_hecho = timezone.make_aware(datetime.datetime(2026, 10, 8, 15, 0))
        HistorialEstado.objects.filter(pk=paso_hecho.pk).update(fecha=fecha_hecho)

        # 4) En revisión (no entregado aún, sí pasó por revisión, sin reproceso)
        cls.e_rev = Entregable.objects.create(
            contrato=cls.c1,
            plantilla=cls.plantilla_matriz,
            titulo="Matriz en Revisión",
            id_tdr="TDR-104",
            fecha_recepcion=datetime.date(2026, 10, 5),
            plazo=datetime.date(2026, 10, 20),
            datos={"c_alcance": "parcial"},
            estado=E.VERIFICACION_SENIOR,
            junior_asignado=cls.j1,
            senior_revisor=cls.s1,
            creado_por=cls.s1,
        )
        Observacion.objects.create(
            entregable=cls.e_rev,
            autor=cls.s1,
            responsable=cls.j1,
            tipo_error=TipoError.DATO_FALTANTE,
            descripcion="Falta anexo",
        )

        # --- Contrato C-OTRO (senior: s2, junior: j2, cliente: Cliente B) ---
        # 5) Entregado a tiempo pero con reproceso (recepción 03/10, entrega 06/10, plazo 12/10 -> 3 días, a tiempo)
        cls.e_otro = Entregable.objects.create(
            contrato=cls.c_otro,
            plantilla=cls.plantilla_matriz,
            titulo="Matriz Cliente B",
            id_tdr="TDR-201",
            fecha_recepcion=datetime.date(2026, 10, 3),
            plazo=datetime.date(2026, 10, 12),
            datos={"c_alcance": "ok"},
            estado=E.HECHO,
            junior_asignado=cls.j2,
            senior_revisor=cls.s2,
            creado_por=cls.s2,
        )
        cls._registrar_entrega(cls.e_otro, cls.s2, datetime.date(2026, 10, 6))
        HistorialEstado.objects.create(
            entregable=cls.e_otro,
            estado_anterior=E.VERIFICACION_SENIOR,
            estado_nuevo=E.EN_PROCESO,
            usuario=cls.s2,
            detalle="Devuelto por contenido",
        )
        cls._registrar_tiempo(cls.e_otro, cls.j2, datetime.datetime(2026, 10, 4, 10, 0), horas=6)
        Observacion.objects.create(
            entregable=cls.e_otro,
            autor=cls.s2,
            responsable=cls.j2,
            tipo_error=TipoError.CONTENIDO,
            descripcion="Revisar conclusiones",
        )

    @classmethod
    def _registrar_entrega(cls, entregable, usuario, fecha_entrega):
        v_final = Adjunto.objects.create(
            entregable=entregable,
            archivo="demo/vfinal.pdf",
            nombre_original="vfinal.pdf",
            tipo=TipoAdjunto.VERSION_FINAL,
            version=1,
            subido_por=usuario,
            bloqueado=True,
        )
        cargo = Adjunto.objects.create(
            entregable=entregable,
            archivo="demo/cargo.pdf",
            nombre_original="cargo.pdf",
            tipo=TipoAdjunto.CARGO_RECEPCION,
            version=1,
            subido_por=usuario,
            bloqueado=True,
        )
        return Entrega.objects.create(
            entregable=entregable,
            numero=1,
            fecha_entrega=fecha_entrega,
            medio=Entrega.Medio.CORREO,
            cargo=cargo,
            version_enviada=v_final,
            registrada_por=usuario,
        )

    @classmethod
    def _registrar_tiempo(cls, entregable, usuario, inicio_naive, horas):
        ini = timezone.make_aware(inicio_naive)
        fin = ini + datetime.timedelta(hours=horas)
        return RegistroTiempo.objects.create(
            entregable=entregable,
            usuario=usuario,
            etapa=RegistroTiempo.Etapa.CONSOLIDACION,
            inicio=ini,
            fin=fin,
        )

    def test_cifras_exactas_para_gerente_y_admin(self):
        # Gerente ve los 5 entregables (4 entregados: e_ok, e_tarde, e_pre_s2, e_otro; 3 a tiempo: e_ok, e_pre_s2, e_otro)
        for usuario in (self.gerente, self.admin):
            with self.subTest(rol=usuario.rol):
                datos = calcular_indicadores(usuario)
                # 1. % a tiempo: 3 de 4 = 75 %
                self.assertEqual(datos["entregados_total"], 4)
                self.assertEqual(datos["a_tiempo_num"], 3)
                self.assertEqual(datos["a_tiempo_pct"], 75)
                # 2. % con reproceso: 2 (e_tarde, e_otro) de 5 que pasaron por revisión = 40 %
                self.assertEqual(datos["revisados_total"], 5)
                self.assertEqual(datos["reproceso_num"], 2)
                self.assertEqual(datos["reproceso_pct"], 40)
                # 3. Tiempo promedio: días = (5 + 14 + 6 + 3) / 4 = 28 / 4 = 7,0 días; horas = (4 + 8 + 6) / 3 = 6,0 h
                self.assertEqual(datos["dias_promedio"], 7.0)
                self.assertEqual(datos["dias_promedio_texto"], "7,0")
                self.assertEqual(datos["horas_promedio"], 6.0)
                self.assertEqual(datos["horas_promedio_texto"], "6,0")
                # 4. Observaciones por tipo de error: 4 en total (2 Formato, 1 Dato faltante, 1 Contenido)
                self.assertEqual(datos["observaciones_total"], 4)
                tipos = {f["tipo_error"]: (f["cantidad"], f["porcentaje"]) for f in datos["por_tipo_error"]}
                self.assertEqual(
                    tipos,
                    {
                        TipoError.FORMATO: (2, 100),
                        TipoError.CONTENIDO: (1, 50),
                        TipoError.DATO_FALTANTE: (1, 50),
                    },
                )

    def test_entregable_cerrado_antes_del_sprint_2_usa_fecha_del_historial(self):
        # e_pre_s2 no tiene registro en Entrega; su fecha de entrega sale del HistorialEstado (08/10/2026 <= plazo 10/10/2026)
        datos = calcular_indicadores(self.j1, {"plantilla": self.plantilla_matriz.pk})
        self.assertEqual(datos["entregados_total"], 1)
        self.assertEqual(datos["a_tiempo_num"], 1)
        self.assertEqual(datos["a_tiempo_pct"], 100)
        self.assertEqual(datos["dias_promedio"], 6.0)  # del 02/10 al 08/10 = 6 días

    def test_desglose_por_tipo_de_entregable(self):
        datos = calcular_indicadores(self.gerente)
        por_plantilla = {f["nombre"]: f for f in datos["por_plantilla"]}
        # Plantilla 1 (cls.plantilla): e_ok (5d, 4h, a tiempo) y e_tarde (14d, 8h, tarde) -> 2 entregados, 9,5d, 6,0h, 50 %
        p1 = por_plantilla[self.plantilla.nombre]
        self.assertEqual(p1["entregados"], 2)
        self.assertEqual(p1["dias_promedio_texto"], "9,5")
        self.assertEqual(p1["horas_promedio_texto"], "6,0")
        self.assertEqual(p1["a_tiempo_pct"], 50)
        # Plantilla 2 (Matriz de riesgos): e_pre_s2 (6d, sin horas, a tiempo) y e_otro (3d, 6h, a tiempo) -> 2 entregados, 4,5d, 6,0h, 100 %
        p2 = por_plantilla["Matriz de riesgos"]
        self.assertEqual(p2["entregados"], 2)
        self.assertEqual(p2["dias_promedio_texto"], "4,5")
        self.assertEqual(p2["horas_promedio_texto"], "6,0")
        self.assertEqual(p2["a_tiempo_pct"], 100)

    def test_visibilidad_por_rol_junior_senior_gerente(self):
        # Junior j1: ve solo los 4 de C1 (3 entregados: 2 a tiempo = 67 %; 4 revisados: 1 reproceso = 25 %; 3 observaciones)
        # y NO tiene tabla «Por responsable».
        datos_j1 = calcular_indicadores(self.j1)
        self.assertFalse(datos_j1["mostrar_por_responsable"])
        self.assertEqual(datos_j1["por_responsable"], [])
        self.assertEqual(datos_j1["entregados_total"], 3)
        self.assertEqual(datos_j1["a_tiempo_num"], 2)
        self.assertEqual(datos_j1["a_tiempo_pct"], 67)
        self.assertEqual(datos_j1["revisados_total"], 4)
        self.assertEqual(datos_j1["reproceso_num"], 1)
        self.assertEqual(datos_j1["reproceso_pct"], 25)
        self.assertEqual(datos_j1["observaciones_total"], 3)

        # Junior j2: ve solo el suyo en C-OTRO (1 entregado a tiempo = 100 %; 1 con reproceso = 100 %; 1 observación)
        datos_j2 = calcular_indicadores(self.j2)
        self.assertFalse(datos_j2["mostrar_por_responsable"])
        self.assertEqual(datos_j2["entregados_total"], 1)
        self.assertEqual(datos_j2["a_tiempo_pct"], 100)
        self.assertEqual(datos_j2["reproceso_pct"], 100)
        self.assertEqual(datos_j2["observaciones_total"], 1)

        # Senior s1: ve los de sus contratos (C1) y SÍ tiene tabla «Por responsable»
        datos_s1 = calcular_indicadores(self.s1)
        self.assertTrue(datos_s1["mostrar_por_responsable"])
        self.assertEqual(datos_s1["entregados_total"], 3)
        self.assertEqual([f["responsable"] for f in datos_s1["por_responsable"]], [self.j1])
        fila_j1 = datos_s1["por_responsable"][0]
        self.assertEqual(
            (fila_j1["entregados"], fila_j1["a_tiempo_pct"], fila_j1["reproceso_pct"], fila_j1["observaciones"]),
            (3, 67, 25, 3),
        )

    def test_filtros_acotan_y_nunca_amplian_la_visibilidad(self):
        # j1 intenta filtrar por cliente_b o responsable j2: obtiene 0 resultados (nunca ve lo ajeno)
        self.assertEqual(calcular_indicadores(self.j1, {"cliente": self.cliente_b.pk})["entregados_total"], 0)
        self.assertEqual(calcular_indicadores(self.j1, {"responsable": self.j2.pk})["entregados_total"], 0)
        self.assertEqual(calcular_indicadores(self.s1, {"cliente": self.cliente_b.pk})["entregados_total"], 0)

        # Filtro por periodo (desde / hasta): del 01/10 al 07/10 solo se entregaron e_ok (06/10) y e_otro (06/10)
        datos_periodo = calcular_indicadores(
            self.gerente, {"desde": "2026-10-01", "hasta": "2026-10-07"}
        )
        self.assertEqual(datos_periodo["entregados_total"], 2)
        self.assertEqual(datos_periodo["a_tiempo_num"], 2)
        self.assertEqual(datos_periodo["a_tiempo_pct"], 100)

    def test_valores_de_filtro_invalidos_o_fuera_de_rango_se_ignoran_sin_error_500(self):
        self.client.force_login(self.gerente)
        for params in (
            {"desde": "no-es-fecha", "hasta": "2026-99-99"},
            {"cliente": "abc", "plantilla": "xyz", "responsable": "???"},
            {"cliente": str(2**63), "plantilla": str(-(2**63) - 1), "responsable": "9" * 100},
        ):
            with self.subTest(params=params):
                r = self.client.get(reverse("indicadores"), params)
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.context["filtros_activos"], {})

    def test_pantalla_muestra_las_cuatro_formulas_y_oculta_por_responsable_al_junior(self):
        # Sin sesión redirige al login
        r_anon = self.client.get(reverse("indicadores"))
        self.assertEqual(r_anon.status_code, 302)

        # Vista del Junior: fórmulas visibles y SIN la tabla «Por responsable»
        self.client.force_login(self.j1)
        r_j1 = self.client.get(reverse("indicadores"))
        self.assertEqual(r_j1.status_code, 200)
        self.assertIn("no-store", r_j1["Cache-Control"])
        self.assertContains(r_j1, "¿Cómo se calcula?", count=4)
        for formula in (FORMULA_A_TIEMPO, FORMULA_REPROCESO, FORMULA_TIEMPO, FORMULA_OBSERVACIONES):
            self.assertContains(r_j1, formula)
        self.assertNotContains(r_j1, "<h2>Por responsable</h2>")

        # Vista del Senior y Gerente: incluye la tabla «Por responsable» y la barra de navegación activa
        for usuario in (self.s1, self.gerente):
            self.client.force_login(usuario)
            r = self.client.get(reverse("indicadores"))
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, "<h2>Por responsable</h2>")
            self.assertContains(r, f'href="{reverse("indicadores")}" aria-current="page">Indicadores</a>')
