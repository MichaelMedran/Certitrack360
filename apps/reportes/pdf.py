"""PDF del reporte de avance con reportlab (SDD del Sprint 3, RF-50). Local: no usa servicios ni fuentes externas.

Hoja A4 apaisada (cabe la tabla de estados). Usa la fuente Helvetica incluida en reportlab, que escribe bien las tildes y la ñ.
"""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

AZUL = colors.HexColor("#1e4e8c")
GRIS = colors.HexColor("#f3f4f6")


def _estilos():
    base = getSampleStyleSheet()
    celda = ParagraphStyle("celda", parent=base["BodyText"], fontSize=8, leading=10)
    return {
        "titulo": ParagraphStyle("titulo", parent=base["Title"], fontSize=18, textColor=AZUL, spaceAfter=4),
        "normal": ParagraphStyle("normal", parent=base["BodyText"], fontSize=10, leading=13),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=12, textColor=AZUL, spaceBefore=10, spaceAfter=4),
        "celda": celda,
        "celda_negrita": ParagraphStyle("celda_negrita", parent=celda, fontName="Helvetica-Bold"),
        "cabecera": ParagraphStyle("cabecera", parent=celda, fontName="Helvetica-Bold", textColor=colors.white, alignment=1),
    }


def _tabla(filas, anchos, negritas=()):
    t = Table(filas, colWidths=anchos, repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9ca3af")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i in negritas:
        estilo.append(("BACKGROUND", (0, i), (-1, i), GRIS))
    t.setStyle(TableStyle(estilo))
    return t


def generar_pdf(datos, datos_al, origen, generado_por=None):
    """Devuelve los bytes del PDF.

    `datos` es el diccionario de `servicios.calcular_datos`; `datos_al`, la fecha y hora (ya en hora local) de los datos.
    """
    s = _estilos()
    p = lambda texto, estilo="celda": Paragraph(escape(str(texto)), s[estilo])
    salida = io.BytesIO()
    doc = SimpleDocTemplate(
        salida, pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title="Reporte de avance de entregables", author="CertiTrack 360",
    )
    historia = [
        Paragraph("Reporte de avance de entregables", s["titulo"]),
        Paragraph(f"<b>Datos al:</b> {datos_al:%d/%m/%Y a las %H:%M} (hora de Lima)", s["normal"]),
        Paragraph(
            f"<b>Origen:</b> {escape(origen)}"
            + (f" · <b>Generado por:</b> {escape(generado_por)}" if generado_por else "")
            + f" · <b>Por vencer:</b> plazo en los próximos {datos['ventana_dias']} días",
            s["normal"],
        ),
        Paragraph("Las cifras salen de los registros de la plataforma; no se ingresan a mano.", s["normal"]),
        Paragraph("Totales del área", s["h2"]),
    ]

    estados = datos["estados"]
    t = datos["totales"]
    cab = [p(x, "cabecera") for x in ("Entregables", "Activos", *[e["etiqueta"] for e in estados],
                                      "Vencidos", "Por vencer", "Observaciones pendientes")]
    fila = [p(t["total"], "celda_negrita"), p(t["activos"], "celda_negrita"), *[p(n, "celda_negrita") for n in t["celdas"]],
            p(t["vencidos"], "celda_negrita"), p(t["por_vencer"], "celda_negrita"), p(t["observaciones_pendientes"], "celda_negrita")]
    historia.append(_tabla([cab, fila], [2.5 * cm] * 2 + [2.4 * cm] * len(estados) + [2.2 * cm, 2.2 * cm, 3.2 * cm]))

    historia.append(Paragraph("Por cliente y contrato", s["h2"]))
    cab = [p(x, "cabecera") for x in ("Cliente", "Contrato", "Total", *[e["etiqueta"] for e in estados],
                                      "Vencidos", "Por vencer", "Obs. pendientes")]
    filas, negritas = [cab], []
    for cliente in datos["clientes"]:
        negritas.append(len(filas))
        filas.append([p(cliente["nombre"], "celda_negrita"), p("Todos los contratos", "celda_negrita"),
                      p(cliente["total"], "celda_negrita"), *[p(n, "celda_negrita") for n in cliente["celdas"]],
                      p(cliente["vencidos"], "celda_negrita"), p(cliente["por_vencer"], "celda_negrita"),
                      p(cliente["observaciones_pendientes"], "celda_negrita")])
        for c in cliente["contratos"]:
            filas.append([p(""), p(c["nombre"]), p(c["total"]), *[p(n) for n in c["celdas"]],
                          p(c["vencidos"]), p(c["por_vencer"]), p(c["observaciones_pendientes"])])
    if len(filas) == 1:
        historia.append(Paragraph("No hay entregables registrados.", s["normal"]))
    else:
        historia.append(_tabla(filas, [4.6 * cm, 3.4 * cm, 1.4 * cm] + [1.9 * cm] * len(estados) + [1.7 * cm, 1.7 * cm, 2.2 * cm],
                               negritas))
    historia.append(Spacer(1, 0.4 * cm))
    historia.append(Paragraph(
        "Vencidos y por vencer no incluyen los entregables ya entregados. Observaciones pendientes: aún sin acción correctiva.",
        s["normal"]))
    doc.build(historia)
    return salida.getvalue()
