"""SDD del Sprint 2, hito S2-H1 · RF-23 (caso 16): las columnas y los estados se llaman como pide HU-04 (Por hacer, En
proceso, Revisión senior, Aprobado, Entregado) y los códigos guardados son los mismos del Sprint 1."""
import re
from pathlib import Path

from django.conf import settings
from django.urls import reverse

from apps.alertas.models import Notificacion
from apps.entregables import servicios
from apps.entregables.models import Entregable, HistorialEstado
from apps.entregables.test_filtros import FiltrosBase
from apps.entregables.testing import entregar

E = Entregable.Estado
HU_04 = ["Por hacer", "En proceso", "Revisión senior", "Aprobado", "Entregado"]
CODIGOS_SPRINT_1 = ["A_REALIZAR", "EN_PROCESO", "VERIFICACION_SENIOR", "LISTO_PARA_ENTREGA", "HECHO"]
ANTIGUAS = ("A realizar", "Verificación senior", "verificación senior", "Listo para entrega", "«Hecho»", "[Hecho]")
RAIZ = Path(settings.BASE_DIR)


class EtiquetasDeHU04Tests(FiltrosBase):
    def test_las_etiquetas_son_las_de_hu_04_y_los_codigos_no_cambian(self):
        self.assertEqual(list(E.labels), HU_04)
        self.assertEqual(list(E.values), CODIGOS_SPRINT_1)

    def test_las_columnas_del_tablero_muestran_las_etiquetas_en_orden(self):
        self.client.force_login(self.gerente)
        html = self.client.get(reverse("tablero")).content.decode()
        columnas = re.findall(r'<h3 id="col-(\w+)">([^<]+?) <span', html)
        self.assertEqual(columnas, list(zip(CODIGOS_SPRINT_1, HU_04)))
        for antigua in ANTIGUAS:
            self.assertNotIn(antigua, html)

    def test_mover_guarda_el_mismo_codigo_de_siempre(self):
        self.client.force_login(self.j1)
        r = self.client.post(reverse("entregable_estado", args=[self.e1.pk]), {"estado": "EN_PROCESO"}, HTTP_HX_REQUEST="true")
        self.assertContains(r, "«E1» pasó a «En proceso».")
        self.assertEqual(Entregable.objects.filter(pk=self.e1.pk).values_list("estado", flat=True).get(), "EN_PROCESO")
        h = HistorialEstado.objects.filter(entregable=self.e1).get()
        self.assertEqual((h.estado_anterior, h.estado_nuevo), ("A_REALIZAR", "EN_PROCESO"))
        self.assertEqual(h.descripcion, "Estado: Por hacer → En proceso")

    def test_el_detalle_ofrece_los_movimientos_con_las_etiquetas_nuevas(self):
        self.client.force_login(self.s1)
        self.assertContains(self.client.get(reverse("entregable_detalle", args=[self.d.pk])), "Pasar a «Aprobado»")
        entregar(self.f, self.gerente)
        self.client.force_login(self.gerente)
        self.assertContains(self.client.get(reverse("entregable_detalle", args=[self.f.pk])), "<strong>Entregado</strong>")

    def test_filtros_lista_inicio_y_consolidado_usan_las_etiquetas(self):
        self.client.force_login(self.gerente)
        lista = self.client.get(reverse("entregables")).content.decode()
        for codigo, etiqueta in zip(CODIGOS_SPRINT_1, HU_04):
            self.assertIn(f'<option value="{codigo}">{etiqueta}</option>', lista)
        self.assertIn("<td>Revisión senior</td>", lista)
        self.assertContains(self.client.get(reverse("inicio")), "</div>En revisión senior</div>")
        consolidado = self.client.get(reverse("consolidado")).content.decode()
        self.assertIn("(todo lo que no está en «Entregado»)", consolidado)

    def test_un_junior_que_ya_no_puede_subir_lee_los_estados_nuevos(self):
        self.client.force_login(self.j2)
        r = self.client.get(reverse("entregable_detalle", args=[self.d.pk]))
        self.assertContains(r, "solo se suben mientras el entregable está en «Por hacer» o «En proceso».")

    def test_el_aviso_de_revision_usa_la_etiqueta_nueva(self):
        servicios.mover(self.e1, E.EN_PROCESO, self.j1)
        servicios.mover(self.e1, E.VERIFICACION_SENIOR, self.j1)
        self.assertIn("pasó a «Revisión senior»", Notificacion.objects.get(tipo="VERIFICACION").mensaje)


class SinTextosFijosAntiguosTests(FiltrosBase):
    """Las etiquetas salen siempre de Entregable.Estado: ninguna plantilla, script ni mensaje del código las repite."""

    def archivos(self):
        yield from (RAIZ / "templates").rglob("*.html")
        yield from (p for p in (RAIZ / "static" / "js").glob("*.js") if not p.name.endswith(".min.js"))
        for p in (RAIZ / "apps").rglob("*.py"):
            if "migrations" in p.parts or p.name.startswith("test") or p.name == "tests.py":
                continue
            yield p

    def test_ningun_archivo_repite_las_etiquetas_antiguas(self):
        for ruta in self.archivos():
            texto = ruta.read_text(encoding="utf-8")
            for antigua in ANTIGUAS:
                with self.subTest(archivo=ruta.relative_to(RAIZ).as_posix(), etiqueta=antigua):
                    self.assertNotIn(antigua, texto)
