"""Archivos ficticios y diminutos para los datos de demostración. Nunca se usan documentos reales."""


def _escapar(texto):
    return texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf_minimo(titulo, lineas):
    """PDF válido de una página con un título y varias líneas de texto (sin dependencias)."""
    contenido = ["BT", "/F1 16 Tf", "72 740 Td", f"({_escapar(titulo)}) Tj", "/F1 11 Tf"]
    for linea in lineas:
        contenido += ["0 -22 Td", f"({_escapar(linea)}) Tj"]
    contenido.append("ET")
    flujo = "\n".join(contenido).encode("cp1252", "replace")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(flujo) + flujo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    salida = bytearray(b"%PDF-1.4\n")
    posiciones = []
    for numero, objeto in enumerate(objetos, start=1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n" % numero + objeto + b"\nendobj\n"
    inicio_xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    for posicion in posiciones:
        salida += b"%010d 00000 n \n" % posicion
    salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, inicio_xref)
    return bytes(salida)


AVISO = "Documento ficticio de demostracion. No contiene datos reales."


def contenido_demo(extension, titulo, detalle):
    """Bytes de un archivo de demostración con la extensión pedida (pdf o txt)."""
    if extension == "pdf":
        return pdf_minimo(titulo, [detalle, AVISO, "Generado por el comando seed_demo de CertiTrack 360."])
    return f"{titulo}\n{detalle}\n{AVISO}\n".encode("utf-8")
