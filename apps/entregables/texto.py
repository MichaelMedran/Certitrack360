"""Texto de un archivo adjunto, para poder buscar dentro de su contenido (buscador global).

Lee el texto que el propio archivo trae: PDF (`pypdf`), Word y PowerPoint (son ZIP con XML), Excel (`openpyxl`) y texto
plano. No hace OCR: una imagen o un PDF escaneado quedan sin texto y se siguen encontrando por su nombre.
Nunca lanza: si el archivo no se puede leer, devuelve "" y la subida continúa.
"""
import io
import logging
import re
import zipfile
from html import unescape

registro = logging.getLogger(__name__)

MAX_CARACTERES = 200_000
MAX_PAGINAS = 200
MAX_CELDAS = 50_000
_ETIQUETA = re.compile(r"<[^>]+>")
_PARRAFO = re.compile(r"</(?:w:p|a:p)>")


def _pdf(contenido):
    from pypdf import PdfReader

    lector = PdfReader(io.BytesIO(contenido))
    partes = []
    for pagina in lector.pages[:MAX_PAGINAS]:
        partes.append(pagina.extract_text() or "")
    return "\n".join(partes)


def _xml_a_texto(xml):
    return unescape(_ETIQUETA.sub("", _PARRAFO.sub("\n", xml)))


def _zip_xml(contenido, es_parte):
    partes = []
    with zipfile.ZipFile(io.BytesIO(contenido)) as paquete:
        for nombre in sorted(n for n in paquete.namelist() if es_parte(n)):
            partes.append(_xml_a_texto(paquete.read(nombre).decode("utf-8", "replace")))
    return "\n".join(partes)


def _docx(contenido):
    return _zip_xml(contenido, lambda n: re.fullmatch(r"word/(document|header\d*|footer\d*)\.xml", n))


def _pptx(contenido):
    return _zip_xml(contenido, lambda n: re.fullmatch(r"ppt/slides/slide\d+\.xml", n))


def _xlsx(contenido):
    from openpyxl import load_workbook

    libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    partes = []
    celdas = 0
    try:
        for hoja in libro.worksheets:
            partes.append(hoja.title)
            for fila in hoja.iter_rows(values_only=True):
                valores = [str(v) for v in fila if v is not None and str(v).strip()]
                celdas += len(valores)
                if valores:
                    partes.append(" ".join(valores))
                if celdas > MAX_CELDAS:
                    return "\n".join(partes)
    finally:
        libro.close()
    return "\n".join(partes)


def _txt(contenido):
    try:
        return contenido.decode("utf-8")
    except UnicodeDecodeError:
        return contenido.decode("latin-1", "replace")


LECTORES = {"pdf": _pdf, "docx": _docx, "pptx": _pptx, "xlsx": _xlsx, "txt": _txt}


def extraer_texto(archivo, nombre=None):
    """Texto del archivo (un `File` de Django o cualquier objeto con `read`), compactado y acotado. "" si no se puede."""
    nombre = nombre or getattr(archivo, "name", "") or ""
    lector = LECTORES.get(nombre.rsplit(".", 1)[-1].lower() if "." in nombre else "")
    if lector is None:
        return ""
    try:
        posicion = archivo.tell() if hasattr(archivo, "tell") else None
        if hasattr(archivo, "seek"):
            archivo.seek(0)
        contenido = archivo.read()
        if posicion is not None:
            archivo.seek(posicion)
        texto = lector(contenido)
    except Exception as exc:  # noqa: BLE001 - archivo dañado, cifrado o con formato inesperado
        registro.info("No se pudo leer el texto de %s: %s", nombre, exc)
        return ""
    # La base de datos no admite el carácter nulo; los espacios repetidos no aportan a la búsqueda.
    texto = re.sub(r"[ \t\r\f\v]+", " ", texto.replace("\x00", " "))
    texto = re.sub(r"\n\s*\n+", "\n", texto).strip()
    return texto[:MAX_CARACTERES]


def fragmento(texto, palabras, ancho=80):
    """Trozo del texto alrededor de la primera palabra buscada que aparece, o "" si ninguna aparece."""
    from apps.busqueda.servicios import patron_insensible

    for palabra in palabras:
        hallazgo = re.search(patron_insensible(palabra), texto, flags=re.IGNORECASE)
        if hallazgo:
            inicio = max(0, hallazgo.start() - ancho)
            fin = min(len(texto), hallazgo.end() + ancho)
            trozo = " ".join(texto[inicio:fin].split())
            return ("… " if inicio else "") + trozo + (" …" if fin < len(texto) else "")
    return ""
