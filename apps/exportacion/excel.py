"""Generación de Excel con openpyxl (SDD del Sprint 3, RF-47, §7.8 y D11).

Con el formato `.xlsx` del cliente (enlazado a la plantilla TDR en el repositorio) se reemplazan los marcadores `{{clave}}`
de todas las celdas de texto de todas las hojas; sin formato, se arma una hoja estándar de dos columnas (Campo, Valor).
Un marcador sin dato conocido queda vacío y se informa. Las fechas llegan ya como texto dd/mm/aaaa.
"""
import re
from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Alignment, Font

MARCADOR = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")
ANCHO_MAXIMO_VALOR = 80


def _asignar(celda, texto):
    """Asigna texto a la celda sin que Excel lo interprete como fórmula aunque empiece con «=»."""
    celda.value = texto
    celda.data_type = "s"


def _hoja_estandar(datos):
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Entregable"
    hoja.append(["Campo", "Valor"])
    for celda in hoja[1]:
        celda.font = Font(bold=True)
    for _clave, etiqueta, valor in datos:
        hoja.append([etiqueta, valor if valor is not None else ""])
    mayor_etiqueta = max((len(str(e)) for _c, e, _v in datos), default=5)
    mayor_valor = max((len(str(v)) for _c, _e, v in datos), default=5)
    hoja.column_dimensions["A"].width = min(max(mayor_etiqueta + 2, 12), 40)
    hoja.column_dimensions["B"].width = min(max(mayor_valor + 2, 20), ANCHO_MAXIMO_VALOR)
    for fila in hoja.iter_rows(min_row=2):
        for celda in fila:
            _asignar(celda, "" if celda.value is None else str(celda.value))
            celda.alignment = Alignment(wrap_text=True, vertical="top")
    hoja.freeze_panes = "A2"
    return libro


def _rellenar_formato(contenido, valores):
    """Abre el `.xlsx` del cliente y reemplaza los marcadores; devuelve (libro, marcadores desconocidos sin repetir)."""
    libro = load_workbook(BytesIO(contenido))
    desconocidos = []

    def reemplazo(coincidencia):
        clave = coincidencia.group(1)
        if clave in valores:
            return valores[clave]
        if clave and clave not in desconocidos:
            desconocidos.append(clave)
        return ""

    for hoja in libro.worksheets:
        for fila in hoja.iter_rows():
            for celda in fila:
                if isinstance(celda, MergedCell) or celda.data_type != "s" or not isinstance(celda.value, str):
                    continue
                if "{{" not in celda.value:
                    continue
                _asignar(celda, MARCADOR.sub(reemplazo, celda.value))
    return libro, desconocidos


def generar(datos, formato=None):
    """Excel del entregable. `datos`: lista de (clave, etiqueta, valor). `formato`: bytes del `.xlsx` del cliente o None.

    Devuelve `(bytes del archivo, marcadores desconocidos, True si se usó el formato del cliente)`.
    """
    desconocidos, uso_formato = [], False
    libro = None
    if formato is not None:
        valores = {}
        for clave, _etiqueta, valor in datos:
            valores.setdefault(clave, "" if valor is None else str(valor))
        libro, desconocidos = _rellenar_formato(formato, valores)
        uso_formato = True
    if libro is None:
        libro = _hoja_estandar(datos)
    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue(), desconocidos, uso_formato
