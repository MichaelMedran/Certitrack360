"""Ayudantes para las pruebas de la extracción: PDF ficticios y un motor de OCR simulado (no exigen Tesseract)."""
import io
from contextlib import contextmanager
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile

from . import motores


def pdf_con_paginas(*paginas, nombre="documento.pdf"):
    """Un PDF real; cada elemento de `paginas` es la lista de líneas de texto de una página (None o [] = página sin texto,
    como un escaneo)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    salida = io.BytesIO()
    lienzo = canvas.Canvas(salida, pagesize=A4)
    for lineas in paginas:
        y = 800
        for linea in lineas or []:
            lienzo.drawString(60, y, linea)
            y -= 18
        if not lineas:
            lienzo.rect(60, 600, 200, 100)  # algo dibujado, pero sin texto: lo que sería un escaneo
        lienzo.showPage()
    lienzo.save()
    return SimpleUploadedFile(nombre, salida.getvalue(), content_type="application/pdf")


def imagen_png(nombre="escaneo.png"):
    from PIL import Image

    salida = io.BytesIO()
    Image.new("RGB", (60, 30), "white").save(salida, format="PNG")
    return SimpleUploadedFile(nombre, salida.getvalue(), content_type="image/png")


@contextmanager
def ocr_simulado(*paginas):
    """Simula Tesseract: cada llamada a `ocr_imagen` devuelve la siguiente página de `paginas`, una lista de
    (texto, confianza). Devuelve el mock de `ocr_imagen` para poder contar las llamadas."""
    pendientes = list(paginas)
    with mock.patch.object(motores, "tesseract_disponible", return_value=True), \
            mock.patch.object(motores, "ocr_imagen", side_effect=lambda *a, **k: pendientes.pop(0) if pendientes else []) as ocr:
        yield ocr


@contextmanager
def sin_ocr():
    """Simula un servidor sin Tesseract instalado."""
    with mock.patch.object(motores, "tesseract_disponible", return_value=False), \
            mock.patch.object(motores, "ocr_imagen", side_effect=AssertionError("no debe llamarse sin OCR")) as ocr:
        yield ocr
