"""Servicios de la extracción de datos (SDD del Sprint 3, §7.9, RF-48).

Regla central: leer un documento solo crea una `Extraccion` (una propuesta). Nada llega a un entregable hasta `confirmar`, y
aun entonces los valores pasan por las mismas validaciones del formulario normal.
"""
import datetime
import os

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.entregables import adjuntos
from apps.entregables.archivos import validar_archivo
from apps.entregables.forms import EntregableForm, contratos_para
from apps.entregables.models import Entregable
from apps.entregables.tipos import TipoAdjunto
from apps.entregables.visibilidad import es_elaborador_del_entregable, es_senior_del_entregable

from . import campos as buscador
from . import motores
from .models import Extraccion

ETIQUETA_MOTOR = {"TEXTO_PDF": "Texto del PDF", "TESSERACT": "OCR Tesseract"}


def puede_extraer(usuario, entregable):
    """Elaboradores y seniors del entregable (y gerente o admin), mientras está en Por hacer o En proceso."""
    return (
        entregable.estado in adjuntos.ESTADOS_INICIALES
        and (es_elaborador_del_entregable(usuario, entregable) or es_senior_del_entregable(usuario, entregable))
    )


def estado_de_motores():
    """Qué motores hay en este servidor, para la nota «Estado de los motores» de la pantalla."""
    return {"texto_pdf": True, "ocr": motores.tesseract_disponible()}


def es_legible(nombre):
    return os.path.splitext(nombre or "")[1].lower().lstrip(".") in motores.EXTENSIONES_LEGIBLES


def _motor(lectura):
    if "TESSERACT" in lectura.motores:
        return Extraccion.Motor.TESSERACT
    if "TEXTO_PDF" in lectura.motores:
        return Extraccion.Motor.TEXTO_PDF
    return Extraccion.Motor.NINGUNO


def extraer(usuario, archivo, plantilla=None, entregable=None):
    """Lee el documento y guarda la propuesta (sin tocar ningún entregable). Lanza ValidationError si no se puede leer.

    Con `entregable` solo se buscan los campos de su plantilla; sin él, también cliente, contrato, ID-TDR y fechas entre los
    contratos que `usuario` puede elegir.
    """
    nombre = validar_archivo(archivo)
    extension = os.path.splitext(nombre)[1].lower().lstrip(".")
    if extension not in motores.EXTENSIONES_LEGIBLES:
        raise ValidationError("Suba un PDF o una imagen (PNG o JPG).")
    contenido = archivo.read()
    lectura = motores.leer(contenido, extension)
    if entregable is not None:
        plantilla = entregable.plantilla
    contratos = [] if entregable is not None else contratos_para(usuario)
    campos = buscador.buscar(lectura.lineas, plantilla, contratos, solo_plantilla=entregable is not None)

    avisos = list(lectura.avisos)
    confianza = lectura.confianza_ocr
    minima = settings.OCR_CONFIANZA_MINIMA
    baja = confianza is not None and confianza < minima
    if baja:
        avisos.insert(0, f"Texto poco legible: la confianza media del OCR es {confianza} (mínimo {minima}). Revise los campos "
                         "resaltados; los que no se encontraron quedan vacíos.")
    faltan = [c["etiqueta"] for c in campos if c["estado"] == buscador.NO_ENCONTRADO]
    if faltan:
        avisos.append("No se encontró: " + ", ".join(faltan) + ". Complételo a mano.")
    dudosos = [c["etiqueta"] for c in campos if c["estado"] == buscador.POCO_LEGIBLE]
    if dudosos and not baja:
        avisos.insert(0, "Texto poco legible en: " + ", ".join(dudosos) + ". Revise esos valores.")
    ilegible = bool(baja or lectura.paginas_sin_texto or dudosos)
    return Extraccion.objects.create(
        usuario=usuario, archivo=ContentFile(contenido, name=nombre), nombre_original=nombre, motor=_motor(lectura),
        texto="\n".join(linea.texto for linea in lectura.lineas), campos=campos, ilegible=ilegible, avisos=avisos,
        plantilla=plantilla, entregable=entregable,
    )


def propias(usuario):
    """Cada usuario ve solo sus extracciones."""
    return Extraccion.objects.filter(usuario=usuario).select_related("entregable__contrato", "plantilla")


def descartar(extraccion):
    """Borra la propuesta y su archivo (no se había aplicado a nada)."""
    archivo = extraccion.archivo
    extraccion.delete()
    if archivo:
        archivo.delete(save=False)


# ------------------------------------------------------------------ confirmar

def _valor_guardable(valor):
    return valor.isoformat() if isinstance(valor, datetime.date) else (valor if isinstance(valor, str) else str(valor))


def validar_valores(extraccion, usuario, valores):
    """Valida los valores editados con los mismos campos del formulario (Poka-Yoke). Devuelve {indice: mensaje} con los
    errores; vacío si todo está bien. Los vacíos no se validan: «no encontrado» se completa a mano."""
    errores = {}
    form = EntregableForm(usuario, extraccion.plantilla)
    for i, campo in enumerate(extraccion.campos):
        valor = (valores[i] if i < len(valores) else "").strip()
        if not valor or not campo["clave"].startswith("campo:"):
            continue
        try:
            form.fields[campo["clave"][len("campo:"):]].clean(valor)
        except (ValidationError, KeyError) as error:
            errores[i] = error.messages[0] if isinstance(error, ValidationError) else "Este campo ya no existe en la plantilla."
    return errores


@transaction.atomic
def confirmar(extraccion, usuario, valores):
    """Aplica la propuesta ya revisada por la persona. `valores` va en el orden de `extraccion.campos`.

    - Extracción hecha en «Nuevo entregable» (sin entregable): solo guarda lo confirmado; la pantalla de creación lo toma como
      valores iniciales y el formulario lo valida como cualquier carga manual.
    - Extracción sobre un entregable: completa los datos de su plantilla (los vacíos no borran nada) y lo anota en el historial.
    Lanza ValidationError (con {indice: mensaje}) si algún valor no pasa la validación: en ese caso no se guarda nada.
    """
    if extraccion.usuario_id != usuario.pk:
        raise PermissionDenied
    if extraccion.aplicada_en:
        raise ValidationError("Esta extracción ya se aplicó.")
    entregable = None
    if extraccion.entregable_id:
        entregable = Entregable.objects.select_for_update().select_related("contrato", "plantilla").get(pk=extraccion.entregable_id)
        if not puede_extraer(usuario, entregable):
            raise PermissionDenied
        errores = validar_valores(extraccion, usuario, valores)
        if errores:
            raise ValidationError({str(i): m for i, m in errores.items()})
    campos = []
    for i, campo in enumerate(extraccion.campos):
        confirmado = (valores[i] if i < len(valores) else "").strip()
        campos.append({**campo, "confirmado": confirmado})
    aplicados = []
    if entregable is not None:
        form = EntregableForm(usuario, entregable.plantilla)
        datos = dict(entregable.datos or {})
        for campo in campos:
            if campo["confirmado"] and campo["clave"].startswith("campo:"):
                nombre = campo["clave"][len("campo:"):]
                datos[nombre] = _valor_guardable(form.fields[nombre].clean(campo["confirmado"]))
                aplicados.append(campo["etiqueta"])
        entregable.datos = datos
        entregable.save(update_fields=["datos"])
        if aplicados:
            adjuntos.registrar_en_historial(
                entregable, usuario,
                f"Completó datos de la plantilla desde un documento ({extraccion.nombre_original}): {', '.join(aplicados)}",
            )
    extraccion.campos = campos
    extraccion.aplicada_en = timezone.now()
    extraccion.save(update_fields=["campos", "aplicada_en"])
    return aplicados


# ------------------------------------------------------------------ «Nuevo entregable»

def pendiente_para_crear(usuario, extraccion_id):
    """La extracción confirmada de este usuario que aún no se usó en un entregable (o None)."""
    try:
        pk = int(extraccion_id)
    except (TypeError, ValueError):
        return None
    return propias(usuario).filter(pk=pk, entregable__isnull=True, aplicada_en__isnull=False).first()


def valores_iniciales(extraccion):
    """Valores confirmados como `initial` del formulario de «Nuevo entregable» (solo los que no quedaron vacíos)."""
    inicial = {}
    for campo in extraccion.campos:
        valor = campo.get("confirmado") or ""
        if not valor:
            continue
        clave = campo["clave"]
        if clave == "cliente":
            continue  # lo da el contrato; se muestra en solo lectura
        nombre = clave[len("campo:"):] if clave.startswith("campo:") else clave
        if campo["tipo"] == "fecha" or clave in ("fecha_recepcion", "plazo"):
            try:
                valor = datetime.date.fromisoformat(valor)
            except ValueError:
                continue
        elif clave == "contrato":
            if not valor.isdigit():
                continue
            valor = int(valor)
        inicial[nombre] = valor
    return inicial


def adjuntar_al_crear(extraccion, entregable, usuario):
    """Al crear el entregable, el documento usado se adjunta como TDR y la extracción queda ligada a él."""
    if extraccion is None or extraccion.entregable_id:
        return None
    with extraccion.archivo.open("rb") as origen:
        contenido = origen.read()
    adjunto = adjuntos.crear_adjunto(
        entregable, usuario, ContentFile(contenido, name=extraccion.nombre_original), TipoAdjunto.TDR,
        "Documento usado para prellenar el entregable",
    )
    extraccion.entregable = entregable
    extraccion.save(update_fields=["entregable"])
    return adjunto
