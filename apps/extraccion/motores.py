"""Motores de lectura de documentos (SDD del Sprint 3, §7.9): texto del propio PDF y OCR local con Tesseract.

Orden: se lee el texto del PDF con `pypdf`; si una página no trae texto, o el archivo es una imagen, se usa Tesseract (cada
página de un PDF se convierte antes en imagen con `pypdfium2`). Tesseract es un programa del servidor (`TESSERACT_CMD`):
sin él se avisa y se sigue a mano (misma degradación que el asistente sin Ollama, RNF-09).

Las pruebas simulan el motor reemplazando `tesseract_disponible` y `ocr_imagen` (ver `testing.py`); nada de aquí exige que
Tesseract esté instalado.
"""
import io
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

AVISO_SIN_OCR = "El OCR no está disponible en este servidor."
EXTENSIONES_IMAGEN = ("png", "jpg", "jpeg")
EXTENSIONES_LEGIBLES = ("pdf", *EXTENSIONES_IMAGEN)
CONFIANZA_TEXTO = 100  # el texto que trae el PDF no tiene errores de lectura


class ErrorOCR(Exception):
    """Tesseract está instalado pero no pudo leer la imagen (idioma faltante, imagen dañada, tiempo agotado)."""


@dataclass
class Linea:
    pagina: int
    texto: str
    confianza: int  # 0 a 100
    ocr: bool = False


@dataclass
class Lectura:
    lineas: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    motores: set = field(default_factory=set)  # «TEXTO_PDF» y/o «TESSERACT»
    paginas_sin_texto: list = field(default_factory=list)
    leidas: int = 0

    @property
    def confianza_ocr(self):
        """Confianza media de las líneas leídas con OCR, o None si no se usó OCR."""
        valores = [linea.confianza for linea in self.lineas if linea.ocr]
        return round(sum(valores) / len(valores)) if valores else None


# ------------------------------------------------------------------ Tesseract

def tesseract_disponible():
    return shutil.which(settings.TESSERACT_CMD) is not None


def ocr_imagen(contenido, sufijo=".png"):
    """Lee una imagen con Tesseract y devuelve [(texto de la línea, confianza 0-100)]. Lanza ErrorOCR si falla."""
    with tempfile.TemporaryDirectory(prefix="certitrack-ocr-") as carpeta:
        ruta = Path(carpeta) / f"pagina{sufijo}"
        ruta.write_bytes(contenido)
        try:
            resultado = subprocess.run(
                [settings.TESSERACT_CMD, str(ruta), "stdout", "-l", settings.OCR_IDIOMAS, "tsv"],
                capture_output=True, timeout=120, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ErrorOCR(f"Tesseract no respondió: {error}") from error
    if resultado.returncode != 0:
        raise ErrorOCR((resultado.stderr or b"").decode("utf-8", "replace").strip() or "Tesseract terminó con error.")
    return _lineas_de_tsv(resultado.stdout.decode("utf-8", "replace"))


def _lineas_de_tsv(tsv):
    """Agrupa las palabras del TSV de Tesseract por línea; la confianza de la línea es la media de sus palabras."""
    grupos = {}
    for fila in tsv.splitlines()[1:]:
        partes = fila.split("\t")
        if len(partes) < 12 or partes[0] != "5":
            continue
        texto = partes[11].strip()
        try:
            confianza = float(partes[10])
        except ValueError:
            continue
        if not texto or confianza < 0:
            continue
        grupos.setdefault(tuple(partes[1:5]), []).append((texto, confianza))
    salida = []
    for palabras in grupos.values():
        salida.append((" ".join(p[0] for p in palabras), round(sum(p[1] for p in palabras) / len(palabras))))
    return salida


# ------------------------------------------------------------------ lectura

def _png_de_pagina(pagina_pdf):
    imagen = pagina_pdf.render(scale=2).to_pil()
    salida = io.BytesIO()
    imagen.save(salida, format="PNG")
    return salida.getvalue()


def _con_ocr(lectura, numero, contenido, sufijo, ocr_disponible):
    """Lee una página con OCR y la anota en `lectura`. Devuelve False si la página queda sin texto."""
    if not ocr_disponible:
        lectura.paginas_sin_texto.append(numero)
        return False
    try:
        lineas = ocr_imagen(contenido, sufijo)
    except ErrorOCR as error:
        lectura.avisos.append(f"El OCR falló en la página {numero}: {error}")
        lineas = []
    lineas = [(t.strip(), c) for t, c in lineas if t and t.strip()]
    if not lineas:
        lectura.paginas_sin_texto.append(numero)
        return False
    lectura.motores.add("TESSERACT")
    lectura.lineas.extend(Linea(numero, texto, int(confianza), ocr=True) for texto, confianza in lineas)
    return True


def leer(contenido, extension):
    """Lee el documento (bytes) y devuelve una `Lectura`. Lanza ValidationError si el archivo no se puede abrir."""
    extension = (extension or "").lower().lstrip(".")
    if extension not in EXTENSIONES_LEGIBLES:
        raise ValidationError("Suba un PDF o una imagen (PNG o JPG).")
    lectura = Lectura()
    ocr_disponible = tesseract_disponible()
    if extension in EXTENSIONES_IMAGEN:
        lectura.leidas = 1
        _con_ocr(lectura, 1, contenido, "." + extension, ocr_disponible)
    else:
        _leer_pdf(lectura, contenido, ocr_disponible)
    if lectura.paginas_sin_texto:
        paginas = ", ".join(str(n) for n in lectura.paginas_sin_texto)
        if not ocr_disponible:
            lectura.avisos.insert(0, f"{AVISO_SIN_OCR} No se pudo leer la página {paginas}: complete esos datos a mano.")
        else:
            lectura.avisos.append(f"La página {paginas} no dio texto: complete esos datos a mano.")
    return lectura


def _leer_pdf(lectura, contenido, ocr_disponible):
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        lector = PdfReader(io.BytesIO(contenido))
        if lector.is_encrypted:
            raise ValidationError("El PDF está protegido con contraseña: quítela y vuelva a subirlo.")
        total = len(lector.pages)
    except ValidationError:
        raise
    except (PyPdfError, ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        raise ValidationError("No se pudo leer el PDF: el archivo está dañado o no es un PDF.") from error
    limite = settings.OCR_MAX_PAGINAS
    if total > limite:
        lectura.avisos.append(f"El documento tiene {total} páginas y solo se leyeron las primeras {limite}.")
    documento_pdfium = None
    for indice in range(min(total, limite)):
        numero = indice + 1
        try:
            texto = lector.pages[indice].extract_text() or ""
        except Exception:  # un PDF mal formado no debe romper la lectura de las demás páginas
            texto = ""
        lectura.leidas += 1
        if texto.strip():
            lectura.motores.add("TEXTO_PDF")
            lectura.lineas.extend(
                Linea(numero, linea.strip(), CONFIANZA_TEXTO) for linea in texto.splitlines() if linea.strip()
            )
            continue
        if not ocr_disponible:
            lectura.paginas_sin_texto.append(numero)
            continue
        try:
            if documento_pdfium is None:
                import pypdfium2

                documento_pdfium = pypdfium2.PdfDocument(contenido)
            png = _png_de_pagina(documento_pdfium[indice])
        except Exception as error:  # noqa: BLE001  (pypdfium2 lanza tipos propios según el fallo)
            lectura.avisos.append(f"No se pudo convertir la página {numero} en imagen: {error}")
            lectura.paginas_sin_texto.append(numero)
            continue
        _con_ocr(lectura, numero, png, ".png", ocr_disponible)
