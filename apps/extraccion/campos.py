"""Búsqueda de los campos del entregable dentro del texto leído (SDD del Sprint 3, §7.9).

Cada campo se busca por su etiqueta («Etiqueta: valor»); cliente y contrato también por coincidencia con los que la persona
puede ver. Un campo es una propuesta con su origen y su confianza; nunca se inventa un valor: lo que no se encuentra queda
vacío y marcado para completarlo a mano (HU-24, criterio 5).
"""
import datetime
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from django.conf import settings

OK, POCO_LEGIBLE, NO_ENCONTRADO = "ok", "poco_legible", "no_encontrado"

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

# clave -> (etiqueta en pantalla, tipo, alias de la etiqueta tal como puede venir en el documento)
CAMPOS_BASE = (
    ("cliente", "Cliente", "texto", ("cliente", "razon social", "empresa")),
    ("contrato", "Número de contrato", "contrato",
     ("numero de contrato", "n de contrato", "nro de contrato", "no de contrato", "contrato", "n contrato")),
    ("id_tdr", "ID-TDR", "texto", ("id tdr", "idtdr", "id del tdr", "id de tdr", "codigo tdr", "codigo del tdr", "tdr", "n de tdr")),
    ("fecha_recepcion", "Fecha de recepción", "fecha",
     ("fecha de recepcion", "recepcion", "recibido el", "recibido", "fecha de solicitud", "fecha de recibido")),
    ("plazo", "Plazo", "fecha",
     ("plazo", "plazo de entrega", "fecha de entrega", "fecha limite", "fecha limite de entrega", "entregar hasta", "vence el")),
)


def normalizar(texto):
    """Minúsculas, sin tildes y con todo lo que no es letra o número reducido a un espacio."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", sin_tildes.lower()).strip()


def parsear_fecha(texto):
    """Primera fecha reconocible en el texto (dd/mm/aaaa, aaaa-mm-dd o «1 de noviembre de 2026»), o None."""
    texto = texto or ""
    candidatos = []
    for m in re.finditer(r"(\d{4})-(\d{1,2})-(\d{1,2})", texto):
        candidatos.append((m.start(), int(m[1]), int(m[2]), int(m[3])))
    for m in re.finditer(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", texto):
        candidatos.append((m.start(), int(m[3]), int(m[2]), int(m[1])))
    for m in re.finditer(r"(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóú]+)\s+(?:de|del)?\s*(\d{4})", texto):
        mes = MESES.get(normalizar(m[2]))
        if mes:
            candidatos.append((m.start(), int(m[3]), mes, int(m[1])))
    for _, anio, mes, dia in sorted(candidatos):
        try:
            return datetime.date(anio, mes, dia)
        except ValueError:
            continue
    return None


def _numero(texto):
    m = re.search(r"-?\d[\d.,\s]*", texto or "")
    if not m:
        return None
    bruto = m[0].strip().replace(" ", "")
    if "," in bruto and "." in bruto:  # el último separador es el decimal
        decimal = "," if bruto.rfind(",") > bruto.rfind(".") else "."
        bruto = bruto.replace("." if decimal == "," else ",", "").replace(decimal, ".")
    else:
        bruto = bruto.replace(",", ".")
    try:
        return str(Decimal(bruto).normalize()) if Decimal(bruto) % 1 else str(int(Decimal(bruto)))
    except InvalidOperation:
        return None


def _con_etiqueta(lineas, alias):
    """Primera línea «Etiqueta: valor» cuya etiqueta es uno de los alias: (línea, valor) o (None, "")."""
    conjunto = {normalizar(a) for a in alias}
    for linea in lineas:
        etiqueta, separador, valor = linea.texto.partition(":")
        if not separador or len(etiqueta) > 60 or not valor.strip():
            continue
        if normalizar(etiqueta) in conjunto:
            return linea, valor.strip()
    return None, ""


def _en_texto(lineas, nombre):
    """Primera línea que contiene el nombre completo (sin tildes ni mayúsculas, por palabras enteras)."""
    buscado = f" {normalizar(nombre)} "
    if buscado.strip() == "":
        return None
    for linea in lineas:
        if buscado in f" {normalizar(linea.texto)} ":
            return linea
    return None


def _item(clave, etiqueta, tipo, valor="", linea=None, origen=None, **extra):
    """Un campo propuesto. El estado sale de si hay valor y de si la línea de origen se leyó con confianza baja."""
    if not valor or linea is None:
        estado, confianza = NO_ENCONTRADO, None
        origen = origen or "No encontrado: completar a mano"
    else:
        confianza = linea.confianza
        estado = POCO_LEGIBLE if confianza < settings.OCR_CONFIANZA_MINIMA else OK
        origen = origen or f"Página {linea.pagina} · «{linea.texto.partition(':')[0].strip()}:»"
        if estado == POCO_LEGIBLE:
            origen = f"Texto poco legible (página {linea.pagina})"
    return {"clave": clave, "etiqueta": etiqueta, "tipo": tipo, "valor": valor, "confianza": confianza,
            "origen": origen, "estado": estado, **extra}


def _campo_de_plantilla(lineas, definicion):
    clave, etiqueta, tipo = f"campo:{definicion['nombre']}", definicion["etiqueta"], definicion.get("tipo", "texto")
    extra = {"opciones": list(definicion.get("opciones", []))} if tipo == "opcion" else {}
    linea, texto = _con_etiqueta(lineas, [etiqueta])
    if linea is None:
        return _item(clave, etiqueta, tipo, **extra)
    valor = ""
    if tipo == "fecha":
        fecha = parsear_fecha(texto)
        valor = fecha.isoformat() if fecha else ""
    elif tipo == "numero":
        valor = _numero(texto) or ""
    elif tipo == "opcion":
        valor = next((o for o in extra["opciones"] if normalizar(o) == normalizar(texto)), "")
    else:
        valor = texto[:255] if tipo == "texto" else texto
    if not valor:  # la etiqueta estaba, pero el valor no se pudo leer como lo que pide el campo
        return _item(clave, etiqueta, tipo, origen=f"No se pudo leer un valor válido (página {linea.pagina}): completar a mano", **extra)
    return _item(clave, etiqueta, tipo, valor, linea, **extra)


def _contrato_y_cliente(lineas, contratos):
    """(item del cliente, item del contrato) contra los contratos que la persona puede elegir."""
    por_numero = {normalizar(c.numero_contrato): c for c in contratos}
    contrato, linea_c = None, None
    linea, texto = _con_etiqueta(lineas, CAMPOS_BASE[1][3])
    if linea is not None:
        contrato = por_numero.get(normalizar(texto))
        if contrato is None:  # «Contrato N.º DEMO-2026-001 (renovación)»: se busca el número dentro del valor
            for numero in sorted(por_numero, key=len, reverse=True):
                if numero and f" {numero} " in f" {normalizar(texto)} ":
                    contrato = por_numero[numero]
                    break
        linea_c = linea if contrato else None
    if contrato is None:  # sin etiqueta: el número de un contrato visible escrito en cualquier parte
        for numero in sorted(por_numero, key=len, reverse=True):
            hallada = _en_texto(lineas, numero)
            if numero and hallada:
                contrato, linea_c = por_numero[numero], hallada
                break
    nombre_contrato = f"{contrato.numero_contrato} · {contrato.cliente.nombre}" if contrato else ""

    clientes = {}
    for c in contratos:
        clientes.setdefault(c.cliente_id, c.cliente)
    cliente, linea_cl = None, None
    linea, texto = _con_etiqueta(lineas, CAMPOS_BASE[0][3])
    if linea is not None:
        valor = normalizar(texto)
        for candidato in sorted(clientes.values(), key=lambda x: len(x.nombre), reverse=True):
            nombre = normalizar(candidato.nombre)
            if nombre and (nombre == valor or f" {nombre} " in f" {valor} " or (len(valor) >= 4 and f" {valor} " in f" {nombre} ")):
                cliente, linea_cl = candidato, linea
                break
    if cliente is None:
        for candidato in sorted(clientes.values(), key=lambda x: len(x.nombre), reverse=True):
            hallada = _en_texto(lineas, candidato.nombre)
            if hallada:
                cliente, linea_cl = candidato, hallada
                break
    item_cliente = _item("cliente", CAMPOS_BASE[0][1], "texto", cliente.nombre if cliente else "", linea_cl)
    if cliente is None and contrato is not None:  # el contrato ya dice de qué cliente es
        item_cliente = _item("cliente", CAMPOS_BASE[0][1], "texto", contrato.cliente.nombre, linea_c, origen="Del contrato encontrado")
    item_contrato = _item(
        "contrato", CAMPOS_BASE[1][1], "contrato", str(contrato.pk) if contrato else "", linea_c,
        origen=None if contrato else "No encontrado entre los contratos que usted puede elegir: completar a mano",
        texto=nombre_contrato,
    )
    return item_cliente, item_contrato


def buscar(lineas, plantilla=None, contratos=(), solo_plantilla=False):
    """Campos propuestos para el documento. Con `solo_plantilla` solo se buscan los de la plantilla (extracción sobre un
    entregable ya creado)."""
    campos = []
    if not solo_plantilla:
        cliente, contrato = _contrato_y_cliente(lineas, list(contratos))
        campos += [cliente, contrato]
        campos.append(_item("id_tdr", CAMPOS_BASE[2][1], "texto", *_texto(lineas, CAMPOS_BASE[2][3], 50)))
        for clave, etiqueta, _, alias in CAMPOS_BASE[3:]:
            linea, texto = _con_etiqueta(lineas, alias)
            fecha = parsear_fecha(texto) if linea else None
            campos.append(
                _item(clave, etiqueta, "fecha", fecha.isoformat() if fecha else "", linea,
                      origen=None if fecha or linea is None else f"No se pudo leer una fecha (página {linea.pagina}): completar a mano")
            )
    for definicion in (plantilla.campos_requeridos if plantilla else []):
        campos.append(_campo_de_plantilla(lineas, definicion))
    return campos


def _texto(lineas, alias, maximo):
    linea, valor = _con_etiqueta(lineas, alias)
    return valor[:maximo], linea
