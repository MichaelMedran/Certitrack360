"""Exportación del entregable a PDF y Excel (SDD del Sprint 3, RF-47: HU-27, §7.8).

Las reglas viven aquí y no en la vista: quién exporta, qué datos se consolidan, qué falta, y la creación del adjunto
versionado con su registro en el historial.
"""
import datetime
import zipfile

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.entregables import adjuntos
from apps.entregables.models import Adjunto, Entregable
from apps.entregables.tipos import TipoAdjunto
from apps.entregables.visibilidad import es_responsable_activo

from . import excel, pdf

PDF, EXCEL = "pdf", "excel"
FORMATOS = {
    PDF: {"nombre": "PDF", "extension": "pdf"},
    EXCEL: {"nombre": "Excel", "extension": "xlsx"},
}
TIPOS_MIME = {
    PDF: "application/pdf",
    EXCEL: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


class FaltanDatos(ValidationError):
    """No se exporta: faltan campos obligatorios. `faltantes` lista exactamente cuáles."""

    def __init__(self, faltantes):
        self.faltantes = list(faltantes)
        super().__init__("No se puede exportar: falta completar " + ", ".join(self.faltantes) + ".", code="faltantes")


def puede_exportar(usuario, entregable):
    """Responsables activos del entregable (junior asignado, apoyo activo, senior del entregable), gerente y admin (§8)."""
    return bool(getattr(usuario, "is_authenticated", False)) and es_responsable_activo(usuario, entregable)


def _fecha(valor):
    return valor.strftime("%d/%m/%Y") if valor else ""


def periodo(entregable):
    """Mes y año del plazo, en español: «noviembre de 2026»."""
    return f"{MESES[entregable.plazo.month - 1]} de {entregable.plazo.year}"


def _valor_campo(campo, valor):
    """Valor de un campo de la plantilla como texto; las fechas ISO se muestran dd/mm/aaaa."""
    if valor is None:
        return ""
    texto = str(valor).strip()
    if campo.get("tipo") == "fecha":
        try:
            return _fecha(datetime.date.fromisoformat(texto))
        except ValueError:
            pass
    return texto


def datos_consolidados(entregable):
    """Lista ordenada de (clave, etiqueta, valor) con lo que se exporta (§7.8): los datos del entregable y, después, cada
    campo de la plantilla con su etiqueta. Las claves son las de los marcadores `{{clave}}` del Excel del cliente."""
    contrato = entregable.contrato
    linea = contrato.linea_servicio.nombre if contrato.linea_servicio_id else "Sin asignar"
    datos = [
        ("codigo", "Código", entregable.codigo or ""),
        ("titulo", "Título", entregable.titulo),
        ("cliente", "Cliente", contrato.cliente.nombre),
        ("contrato", "Contrato", contrato.numero_contrato),
        ("linea_servicio", "Línea de servicio", linea),
        ("id_tdr", "ID-TDR", entregable.id_tdr or ""),
        ("numero_reporte", "N.º de reporte", str(entregable.numero_correlativo or "")),
        ("periodo", "Periodo", periodo(entregable)),
        ("fecha_recepcion", "Fecha de recepción", _fecha(entregable.fecha_recepcion)),
        ("plazo", "Plazo", _fecha(entregable.plazo)),
        ("estado", "Estado", entregable.get_estado_display()),
        ("junior", "Responsable junior", entregable.junior_asignado.nombre),
        ("senior", "Responsable senior", entregable.senior_revisor.nombre),
    ]
    for campo in entregable.plantilla.campos_requeridos:
        datos.append((campo["nombre"], campo["etiqueta"], _valor_campo(campo, entregable.datos.get(campo["nombre"]))))
    return datos


def faltantes(entregable):
    """Lo que impide exportar: el ID-TDR, la fecha de recepción y los campos obligatorios de la plantilla sin completar."""
    pendientes = []
    if not (entregable.id_tdr or "").strip():
        pendientes.append("ID-TDR")
    if not entregable.fecha_recepcion:
        pendientes.append("Fecha de recepción")
    for campo in entregable.plantilla.campos_requeridos:
        if str(entregable.datos.get(campo["nombre"], "")).strip() == "":
            pendientes.append(campo["etiqueta"])
    return pendientes


def formato_excel_del_cliente(entregable):
    """Bytes del `.xlsx` vigente de la plantilla del cliente en el repositorio, o None si no hay uno utilizable (D11)."""
    documento = entregable.plantilla.documento_formato
    if documento is None:
        return None
    version = documento.version_vigente
    if version is None or not version.archivo.name.lower().endswith(".xlsx"):
        return None
    try:
        with version.archivo.open("rb") as origen:
            return origen.read()
    except (FileNotFoundError, ValueError, OSError):
        return None


def formato_de(adjunto):
    """Código de formato («pdf» o «excel») de una exportación ya creada, según su extensión."""
    return EXCEL if adjunto.nombre_original.lower().endswith(".xlsx") else PDF


def exportaciones(entregable):
    """Exportaciones anteriores del entregable, de la más nueva a la más antigua, con su formato."""
    lista = list(
        Adjunto.objects.filter(entregable=entregable, tipo=TipoAdjunto.EXPORTACION)
        .select_related("subido_por")
        .order_by("-version")
    )
    for a in lista:
        a.formato = FORMATOS[formato_de(a)]["nombre"]
    return lista


def _generar_excel(entregable, datos):
    """(bytes, comentario). Si el formato del cliente no se puede abrir, usa el estándar y lo dice en el comentario."""
    base = formato_excel_del_cliente(entregable)
    if base is not None:
        try:
            contenido, desconocidos, _ = excel.generar(datos, base)
        except (zipfile.BadZipFile, KeyError, ValueError, OSError):
            contenido, _, _ = excel.generar(datos)
            return contenido, "Exportación a Excel (el formato del cliente no se pudo abrir; se usó el estándar)"
        comentario = "Exportación a Excel"
        if desconocidos:
            comentario += "; marcadores sin dato: " + ", ".join(desconocidos)
        return contenido, comentario
    contenido, _, _ = excel.generar(datos)
    return contenido, "Exportación a Excel"


@transaction.atomic
def exportar(entregable, usuario, formato, ahora=None):
    """Valida, genera el archivo y lo guarda como una versión nueva del entregable (tipo Exportación). Devuelve el adjunto.

    - 403 (`PermissionDenied`) si el usuario no es responsable del entregable, gerente o admin.
    - `FaltanDatos` (un `ValidationError`) si faltan campos obligatorios: no se genera nada ni se crea adjunto.
    - Registra en el historial quién exportó y cuándo, sin sobrescribir nunca una exportación anterior.
    """
    if formato not in FORMATOS:
        raise ValidationError("Elija el formato de exportación: PDF o Excel.")
    if not puede_exportar(usuario, entregable):
        raise PermissionDenied("Solo los responsables del entregable, el gerente y el admin pueden exportarlo.")
    pendientes = faltantes(entregable)
    if pendientes:
        raise FaltanDatos(pendientes)

    # Bloquea el entregable para conocer la versión que recibirá el archivo y ponerla en su nombre.
    Entregable.objects.select_for_update().get(pk=entregable.pk)
    ultima = (
        Adjunto.objects.filter(entregable=entregable, tipo=TipoAdjunto.EXPORTACION).aggregate(m=Max("version"))["m"] or 0
    )
    version = ultima + 1
    ahora = timezone.localtime(ahora or timezone.now())
    datos = datos_consolidados(entregable)

    if formato == PDF:
        contenido = pdf.generar(entregable, datos, f"Exportado por {usuario.nombre} el {ahora:%d/%m/%Y %H:%M}")
        comentario = "Exportación a PDF"
    else:
        contenido, comentario = _generar_excel(entregable, datos)
    nombre = f"{entregable.codigo or f'entregable-{entregable.pk}'}_v{version}.{FORMATOS[formato]['extension']}"
    nombre_formato = FORMATOS[formato]["nombre"]
    adjunto = adjuntos.crear_adjunto(
        entregable, usuario, ContentFile(contenido, name=nombre), TipoAdjunto.EXPORTACION, comentario,
        detalle=lambda a: f"Exportó el entregable a {nombre_formato} (v{a.version}, {a.nombre_original})",
    )
    return adjunto
