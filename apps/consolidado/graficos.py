"""Gráficos gerenciales dibujados como SVG en el servidor (SDD del Sprint 3, RF-49 y RNF-15).

Son funciones puras: reciben datos y devuelven texto SVG ya escapado (`mark_safe`). No usan JavaScript ni bibliotecas:
el navegador solo dibuja un SVG estático. Cada gráfico lleva `role="img"`, un título y una descripción para los lectores
de pantalla, y el valor de cada barra siempre aparece escrito (el color nunca es la única señal).

`filas` es una lista de `(etiqueta, valor, texto_del_valor)`.
"""
from django.utils.html import escape
from django.utils.safestring import mark_safe

COLOR_BARRA = "#1e4e8c"  # azul oscuro: contraste 8,6:1 sobre blanco
COLOR_TEXTO = "#1f2937"  # contraste 14:1 sobre blanco
COLOR_EJE = "#6b7280"
COLOR_FONDO_BARRA = "#e5e7eb"

ANCHO = 640
ALTO_FILA = 30
ANCHO_ETIQUETA = 210
MARGEN = 12
MAX_ETIQUETA = 30


def _corto(texto, largo=MAX_ETIQUETA):
    texto = str(texto)
    return texto if len(texto) <= largo else texto[: largo - 1] + "…"


def _encabezado(titulo, descripcion, ancho, alto):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" class="grafico-svg" viewBox="0 0 {ancho} {alto}" '
        f'role="img" aria-label="{escape(titulo)}" preserveAspectRatio="xMidYMid meet">'
        f"<title>{escape(titulo)}</title><desc>{escape(descripcion)}</desc>"
    )


def _descripcion(filas):
    return "; ".join(f"{etiqueta}: {texto}" for etiqueta, _, texto in filas)


def barras_horizontales(titulo, filas, maximo=None):
    """Barras horizontales: una fila por elemento, con la etiqueta a la izquierda y el valor escrito al final.

    Devuelve una cadena vacía si no hay filas (la pantalla muestra entonces «No hay datos…»).
    """
    if not filas:
        return mark_safe("")
    tope = maximo if maximo else (max(valor for _, valor, _ in filas) or 1)
    ancho_barra = ANCHO - ANCHO_ETIQUETA - 90 - MARGEN
    alto = ALTO_FILA * len(filas) + 2 * MARGEN
    partes = [_encabezado(titulo, _descripcion(filas), ANCHO, alto)]
    for i, (etiqueta, valor, texto) in enumerate(filas):
        y = MARGEN + i * ALTO_FILA
        largo = max(2.0, ancho_barra * valor / tope) if valor > 0 else 0
        barra = (f'<rect x="{ANCHO_ETIQUETA}" y="{y + 4}" width="{largo:.1f}" height="20" rx="3" fill="{COLOR_BARRA}"/>'
                 if largo else "")
        partes.append(
            f"<g><title>{escape(etiqueta)}: {escape(texto)}</title>"
            f'<text x="{ANCHO_ETIQUETA - 8}" y="{y + 18}" text-anchor="end" font-size="13" fill="{COLOR_TEXTO}">'
            f"{escape(_corto(etiqueta))}</text>"
            f'<rect x="{ANCHO_ETIQUETA}" y="{y + 4}" width="{ancho_barra}" height="20" rx="3" fill="{COLOR_FONDO_BARRA}"/>'
            f"{barra}"
            f'<text x="{ANCHO_ETIQUETA + ancho_barra + 8}" y="{y + 19}" font-size="13" font-weight="700" '
            f'fill="{COLOR_TEXTO}">{escape(texto)}</text></g>'
        )
    partes.append("</svg>")
    return mark_safe("".join(partes))


def barras_verticales(titulo, filas, maximo=100):
    """Barras verticales (p. ej. un porcentaje por mes). `maximo` es el valor que llena la altura (por defecto 100)."""
    if not filas:
        return mark_safe("")
    alto, base, tope_y = 260, 215, 40
    ancho = max(ANCHO, 2 * MARGEN + 70 * len(filas))
    paso = (ancho - 2 * MARGEN) / len(filas)
    ancho_barra = min(48, paso * 0.6)
    altura_util = base - tope_y
    partes = [_encabezado(titulo, _descripcion(filas), ancho, alto)]
    partes.append(f'<line x1="{MARGEN}" y1="{base}" x2="{ancho - MARGEN}" y2="{base}" stroke="{COLOR_EJE}" stroke-width="1"/>')
    for i, (etiqueta, valor, texto) in enumerate(filas):
        x = MARGEN + i * paso + (paso - ancho_barra) / 2
        centro = x + ancho_barra / 2
        altura = max(2.0, altura_util * min(valor, maximo) / maximo) if valor > 0 else 0
        barra = (f'<rect x="{x:.1f}" y="{base - altura:.1f}" width="{ancho_barra:.1f}" height="{altura:.1f}" rx="3" '
                 f'fill="{COLOR_BARRA}"/>' if altura else "")
        partes.append(
            f"<g><title>{escape(etiqueta)}: {escape(texto)}</title>{barra}"
            f'<text x="{centro:.1f}" y="{base - altura - 6:.1f}" text-anchor="middle" font-size="13" font-weight="700" '
            f'fill="{COLOR_TEXTO}">{escape(texto)}</text>'
            f'<text x="{centro:.1f}" y="{base + 20}" text-anchor="middle" font-size="12" fill="{COLOR_TEXTO}">'
            f"{escape(_corto(etiqueta, 12))}</text></g>"
        )
    partes.append("</svg>")
    return mark_safe("".join(partes))


def _num(valor):
    """Un número con coma decimal española y sin ceros sobrantes (6,5 · 12)."""
    return f"{valor:.1f}".replace(".", ",").removesuffix(",0")


def armar_graficos(datos):
    """Convierte los datos de `servicios.datos_graficos` en lo que pinta la plantilla.

    Devuelve una lista de cuatro diccionarios: `id`, `titulo`, `pregunta` (qué mide), `svg` (vacío si no hay datos),
    `columnas` y `filas` de la tabla de datos que va debajo, y `vacio` (texto «No hay datos…»).
    """
    personas = [(f"{p['nombre']} ({p['rol']})", p["activos"], str(p["activos"])) for p in datos["activos_por_persona"]]
    cumplidos = [(m["mes"], m["porcentaje"], f"{m['porcentaje']} %") for m in datos["cumplidos_por_mes"]]
    atencion = [(c["cliente"], c["dias_promedio"], f"{_num(c['dias_promedio'])} d") for c in datos["atencion_por_cliente"]]
    errores = [(o["etiqueta"], o["cantidad"], str(o["cantidad"])) for o in datos["observaciones_por_tipo"]]
    return [
        {
            "id": "g-personas", "titulo": "Entregables activos por persona",
            "pregunta": "Entregables que no están en «Entregado», por responsable (junior y senior).",
            "svg": barras_horizontales("Entregables activos por persona", personas),
            "columnas": ["Persona", "Rol", "Activos"],
            "filas": [[p["nombre"], p["rol"], p["activos"]] for p in datos["activos_por_persona"]],
            "vacio": "No hay datos de entregables activos con este filtro.",
        },
        {
            "id": "g-cumplidos", "titulo": "Entregables cumplidos dentro del plazo",
            "pregunta": "Porcentaje de entregados cuya entrega fue en la fecha de plazo o antes, por mes de entrega.",
            "svg": barras_verticales("Entregables cumplidos dentro del plazo, por mes", cumplidos, maximo=100),
            "columnas": ["Mes", "Entregados", "A tiempo", "Porcentaje"],
            "filas": [[m["mes"], m["entregados"], m["a_tiempo"], f"{m['porcentaje']} %"] for m in datos["cumplidos_por_mes"]],
            "vacio": "No hay datos de entregas con este filtro.",
        },
        {
            "id": "g-atencion", "titulo": "Tiempo promedio de atención por cliente",
            "pregunta": "Días promedio entre la recepción y la entrega de los entregables ya entregados.",
            "svg": barras_horizontales("Tiempo promedio de atención por cliente, en días", atencion),
            "columnas": ["Cliente", "Entregados", "Días promedio"],
            "filas": [[c["cliente"], c["entregados"], _num(c["dias_promedio"])] for c in datos["atencion_por_cliente"]],
            "vacio": "No hay datos de entregas con este filtro.",
        },
        {
            "id": "g-errores", "titulo": "Observaciones por tipo de error",
            "pregunta": "Cantidad de observaciones registradas, por tipo de error.",
            "svg": barras_horizontales("Observaciones por tipo de error", errores),
            "columnas": ["Tipo de error", "Observaciones"],
            "filas": [[o["etiqueta"], o["cantidad"]] for o in datos["observaciones_por_tipo"]],
            "vacio": "No hay observaciones registradas con este filtro.",
        },
    ]
