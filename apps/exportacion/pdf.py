"""Generación de PDF con reportlab (SDD del Sprint 3, RF-47 y §7.8).

Documento A4 estándar: encabezado «CertiTrack 360 · CERTICOM» en todas las páginas, título y subtítulo, tablas con ajuste de
línea (los textos largos se parten en varias líneas dentro de su celda) y pie con un texto y el número de página.

Las fuentes estándar de PDF (Helvetica) cubren las tildes y la «ñ». `documento_tabular` es reutilizable: el hito de reportes
(RF-50) la usa para sus propios PDF.
"""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ENCABEZADO = "CertiTrack 360 · CERTICOM"
AZUL = colors.HexColor("#1f3a5f")
GRIS = colors.HexColor("#555555")
LINEA = colors.HexColor("#c8cdd4")
FONDO_ENCABEZADO = colors.HexColor("#e8edf3")

MARGEN_LATERAL = 18 * mm
ANCHO_UTIL = A4[0] - 2 * MARGEN_LATERAL

ESTILO_TITULO = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=AZUL, spaceAfter=2)
ESTILO_SUBTITULO = ParagraphStyle("subtitulo", fontName="Helvetica", fontSize=10, leading=13, textColor=GRIS, spaceAfter=10)
ESTILO_SECCION = ParagraphStyle(
    "seccion", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=AZUL, spaceBefore=10, spaceAfter=4
)
ESTILO_CELDA = ParagraphStyle("celda", fontName="Helvetica", fontSize=9, leading=12)
ESTILO_ETIQUETA = ParagraphStyle("etiqueta", parent=ESTILO_CELDA, fontName="Helvetica-Bold")
ESTILO_ENCABEZADO_TABLA = ParagraphStyle("encabezado_tabla", parent=ESTILO_CELDA, fontName="Helvetica-Bold", textColor=AZUL)
ESTILO_VACIO = ParagraphStyle("vacio", parent=ESTILO_CELDA, textColor=GRIS)


def _texto(valor):
    """Texto seguro para un `Paragraph` (que interpreta marcas): escapado y con los saltos de línea conservados."""
    return escape("" if valor is None else str(valor)).replace("\r\n", "\n").replace("\n", "<br/>")


MAX_CELDA = 1200  # caracteres por fila de tabla (unas 20 líneas): cabe holgadamente en una página


def _trocear(valor):
    """Parte un texto muy largo en trozos de hasta `MAX_CELDA` caracteres, cortando en un espacio o salto si lo hay."""
    texto = "" if valor is None else str(valor)
    trozos = []
    while len(texto) > MAX_CELDA:
        corte = max(texto.rfind(" ", 0, MAX_CELDA), texto.rfind("\n", 0, MAX_CELDA))
        corte = corte if corte > MAX_CELDA // 2 else MAX_CELDA
        trozos.append(texto[:corte])
        texto = texto[corte:].lstrip(" \n")
    trozos.append(texto)
    return trozos


def _tabla(seccion):
    """Tabla de una sección: `encabezados` opcional y `filas` (secuencias de celdas). Sin encabezados y con dos columnas,
    es una tabla «campo / valor» con la etiqueta en negrita."""
    encabezados = list(seccion.get("encabezados") or [])
    filas = [list(f) for f in seccion.get("filas") or []]
    columnas = len(encabezados) or max((len(f) for f in filas), default=2)
    campo_valor = not encabezados and columnas == 2
    if campo_valor:
        anchos = [ANCHO_UTIL * 0.32, ANCHO_UTIL * 0.68]
    else:
        anchos = [ANCHO_UTIL / columnas] * columnas

    datos = []
    if encabezados:
        datos.append([Paragraph(_texto(h), ESTILO_ENCABEZADO_TABLA) for h in encabezados])
    for fila in filas:
        fila = (fila + [""] * (columnas - len(fila)))[:columnas]
        # Una celda no se parte entre páginas: un texto larguísimo continúa en filas siguientes, sin romper el documento.
        trozos = [_trocear(valor) for valor in fila]
        for n in range(max(len(t) for t in trozos)):
            celdas = []
            for i, partes in enumerate(trozos):
                estilo = ESTILO_ETIQUETA if (campo_valor and i == 0) else ESTILO_CELDA
                celdas.append(Paragraph(_texto(partes[n] if n < len(partes) else ""), estilo))
            datos.append(celdas)

    tabla = Table(datos, colWidths=anchos, repeatRows=1 if encabezados else 0)
    estilo = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, LINEA),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if encabezados:
        estilo.append(("BACKGROUND", (0, 0), (-1, 0), FONDO_ENCABEZADO))
    if campo_valor:
        estilo.append(("BACKGROUND", (0, 0), (0, -1), FONDO_ENCABEZADO))
    tabla.setStyle(TableStyle(estilo))
    return tabla


def documento_tabular(titulo, subtitulo, secciones, pie=""):
    """PDF A4 con encabezado, título, secciones con tablas y pie. Devuelve los bytes del archivo.

    - `titulo`: título del documento (texto).
    - `subtitulo`: línea bajo el título (texto; puede ser vacío).
    - `secciones`: lista de dicts `{"titulo": str o None, "encabezados": [str, ...] (opcional), "filas": [[celda, ...], ...]}`.
      Sin `encabezados` y con filas de dos celdas se dibuja una tabla «campo / valor». Las celdas son texto plano (se
      escapa; los saltos de línea se respetan) y se ajustan a varias líneas si son largas. Una sección sin filas muestra
      «Sin datos.».
    - `pie`: texto del pie de cada página (p. ej. «Exportado por … el 10/11/2026 09:30»); a su derecha va «Página N».
    """
    elementos = [Paragraph(_texto(titulo), ESTILO_TITULO)]
    if subtitulo:
        elementos.append(Paragraph(_texto(subtitulo), ESTILO_SUBTITULO))
    else:
        elementos.append(Spacer(1, 6))
    for seccion in secciones or []:
        if seccion.get("titulo"):
            elementos.append(Paragraph(_texto(seccion["titulo"]), ESTILO_SECCION))
        if seccion.get("filas"):
            elementos.append(_tabla(seccion))
        else:
            elementos.append(Paragraph("Sin datos.", ESTILO_VACIO))

    def decorar(lienzo, doc):
        ancho, alto = A4
        lienzo.saveState()
        lienzo.setFont("Helvetica-Bold", 9)
        lienzo.setFillColor(AZUL)
        lienzo.drawString(MARGEN_LATERAL, alto - 12 * mm, ENCABEZADO)
        lienzo.setStrokeColor(LINEA)
        lienzo.line(MARGEN_LATERAL, alto - 14 * mm, ancho - MARGEN_LATERAL, alto - 14 * mm)
        lienzo.line(MARGEN_LATERAL, 15 * mm, ancho - MARGEN_LATERAL, 15 * mm)
        lienzo.setFont("Helvetica", 8)
        lienzo.setFillColor(GRIS)
        lienzo.drawString(MARGEN_LATERAL, 10 * mm, str(pie or "")[:140])
        lienzo.drawRightString(ancho - MARGEN_LATERAL, 10 * mm, f"Página {doc.page}")
        lienzo.restoreState()

    salida = BytesIO()
    documento = SimpleDocTemplate(
        salida, pagesize=A4, leftMargin=MARGEN_LATERAL, rightMargin=MARGEN_LATERAL, topMargin=22 * mm, bottomMargin=20 * mm,
        title=str(titulo), author="CertiTrack 360 · CERTICOM",
    )
    documento.build(elementos, onFirstPage=decorar, onLaterPages=decorar)
    return salida.getvalue()


def generar(entregable, datos, pie):
    """PDF del entregable (RF-47): título, código y la tabla de datos consolidados (`datos`: lista de (clave, etiqueta, valor))."""
    filas = [(etiqueta, valor if valor not in (None, "") else "—") for _clave, etiqueta, valor in datos]
    return documento_tabular(
        entregable.titulo,
        f"Código {entregable.codigo or '—'}",
        [{"titulo": "Datos del entregable", "filas": filas}],
        pie,
    )
