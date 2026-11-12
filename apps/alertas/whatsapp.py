"""Canal de WhatsApp para los avisos (opcional, apagado por defecto).

Es la única salida a internet de la plataforma además de Filedoc, y solo existe si el administrador la configura
(`WHATSAPP_CONECTOR` en el archivo .env). Sin configurar, nada cambia: los avisos quedan dentro de la plataforma.

Funciona como una cola: cada aviso reciente de un colaborador con celular registrado genera un `EnvioWhatsApp`
pendiente, y el programador (o la alerta urgente, de inmediato) lo despacha. Un fallo de red no pierde el mensaje:
se reintenta hasta `WHATSAPP_MAX_INTENTOS` veces y queda registrado el motivo.
"""
import datetime
import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

registro = logging.getLogger(__name__)

# Solo se encolan avisos recientes: al activar el canal no se reenvía todo el historial.
VENTANA_HORAS = 24
TIEMPO_ESPERA_SEGUNDOS = 10


class ErrorEnvio(Exception):
    """El proveedor rechazó el mensaje o no se pudo llegar a él."""


def activo():
    return bool(settings.WHATSAPP_CONECTOR)


def normalizar_celular(texto):
    """Devuelve el número en formato internacional, solo dígitos (p. ej. 51987654321), o "" si viene vacío.

    Acepta espacios, guiones, paréntesis y el signo +. Un número local sin código de país recibe
    `WHATSAPP_PREFIJO_PAIS`. Lanza ValidationError si no parece un celular.
    """
    texto = (texto or "").strip()
    if not texto:
        return ""
    if re.search(r"[^\d\s()+\-.]", texto):
        raise ValidationError("El celular solo puede llevar números, espacios, guiones y el signo +.")
    internacional = texto.startswith("+") or texto.startswith("00")
    digitos = re.sub(r"\D", "", texto)
    if texto.startswith("00"):
        digitos = digitos[2:]
    prefijo = settings.WHATSAPP_PREFIJO_PAIS
    if not internacional and not (digitos.startswith(prefijo) and len(digitos) > 9):
        digitos = prefijo + digitos.lstrip("0")
    if not 10 <= len(digitos) <= 15:
        raise ValidationError("El celular debe tener entre 10 y 15 dígitos contando el código de país.")
    return digitos


def texto_de(notificacion):
    """Texto del mensaje: el aviso y, si se configuró `SITIO_URL`, la dirección para abrirlo."""
    texto = " ".join(notificacion.mensaje.split())  # las plantillas de WhatsApp no aceptan saltos de línea
    destino = notificacion.destino
    if settings.SITIO_URL and destino:
        texto += f" {settings.SITIO_URL}{destino}"
    return texto


class ConectorMeta:
    """API de WhatsApp Business en la nube (Meta). Envía una plantilla aprobada con el aviso como único parámetro.

    Meta solo permite iniciar una conversación con una plantilla aprobada; la plantilla debe tener un cuerpo con una
    variable, por ejemplo: «CertiTrack 360: {{1}}».
    """

    def enviar(self, numero, texto):
        faltan = [n for n in ("WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID", "WHATSAPP_PLANTILLA") if not getattr(settings, n)]
        if faltan:
            raise ErrorEnvio("Falta configurar " + ", ".join(faltan) + ".")
        cuerpo = {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "template",
            "template": {
                "name": settings.WHATSAPP_PLANTILLA,
                "language": {"code": settings.WHATSAPP_PLANTILLA_IDIOMA},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": texto[:1000]}]}],
            },
        }
        peticion = urllib.request.Request(
            f"{settings.WHATSAPP_API_URL}/{settings.WHATSAPP_PHONE_ID}/messages",
            data=json.dumps(cuerpo).encode("utf-8"),
            headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(peticion, timeout=TIEMPO_ESPERA_SEGUNDOS) as respuesta:  # noqa: S310
                datos = json.loads(respuesta.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            detalle = exc.read().decode("utf-8", "replace")[:300]
            raise ErrorEnvio(f"WhatsApp respondió {exc.code}: {detalle}") from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ErrorEnvio(f"No se pudo conectar con WhatsApp: {exc}") from exc
        mensajes = datos.get("messages") or [{}]
        return mensajes[0].get("id", "")


class ConectorRegistro:
    """Para probar la cola sin cuenta de WhatsApp: escribe el mensaje en el registro del servidor y lo da por enviado."""

    def enviar(self, numero, texto):
        registro.info("WhatsApp (simulado) a %s: %s", numero, texto)
        return "simulado"


def conector():
    return import_string(settings.WHATSAPP_CONECTOR)()


def encolar(ahora=None):
    """Crea un envío pendiente por cada aviso reciente que aún no lo tiene. Devuelve cuántos creó."""
    from .models import EnvioWhatsApp, Notificacion

    if not activo():
        return 0
    ahora = ahora or timezone.now()
    avisos = Notificacion.objects.filter(
        envio_whatsapp__isnull=True, creada_en__gte=ahora - datetime.timedelta(hours=VENTANA_HORAS),
        usuario__is_active=True,
    ).exclude(usuario__celular="").select_related("usuario")
    if settings.WHATSAPP_TIPOS:
        avisos = avisos.filter(tipo__in=settings.WHATSAPP_TIPOS)
    creados = 0
    for aviso in avisos.order_by("pk"):
        # get_or_create: dos procesos que encolan a la vez no duplican el mensaje (la relación es uno a uno).
        _, nuevo = EnvioWhatsApp.objects.get_or_create(notificacion=aviso, defaults={"numero": aviso.usuario.celular})
        creados += nuevo
    return creados


def despachar(limite=100, ahora=None):
    """Encola lo nuevo y envía lo pendiente. Devuelve (enviados, fallidos). Nunca lanza: un fallo se registra."""
    from .models import EnvioWhatsApp

    if not activo():
        return 0, 0
    encolar(ahora)
    enviados = fallidos = 0
    try:
        canal = conector()
    except Exception:  # noqa: BLE001 - conector mal escrito en la configuración
        registro.exception("WHATSAPP_CONECTOR no se pudo cargar")
        return 0, 0
    pendientes = EnvioWhatsApp.objects.filter(estado=EnvioWhatsApp.Estado.PENDIENTE).select_related(
        "notificacion", "notificacion__entregable").order_by("pk")[:limite]
    for envio in pendientes:
        # Se reclama con un UPDATE condicional: si el programador y una alerta urgente coinciden, solo uno lo envía.
        reclamado = EnvioWhatsApp.objects.filter(pk=envio.pk, estado=EnvioWhatsApp.Estado.PENDIENTE).update(
            estado=EnvioWhatsApp.Estado.ENVIANDO)
        if not reclamado:
            continue
        envio.intentos += 1
        try:
            envio.id_externo = (canal.enviar(envio.numero, texto_de(envio.notificacion)) or "")[:100]
        except Exception as exc:  # noqa: BLE001 - cualquier fallo del proveedor: se reintenta luego
            envio.error = str(exc)[:500]
            agotado = envio.intentos >= settings.WHATSAPP_MAX_INTENTOS
            envio.estado = EnvioWhatsApp.Estado.FALLIDO if agotado else EnvioWhatsApp.Estado.PENDIENTE
            fallidos += 1
            registro.warning("WhatsApp no enviado (aviso %s, intento %s): %s", envio.notificacion_id, envio.intentos, exc)
        else:
            envio.estado = EnvioWhatsApp.Estado.ENVIADO
            envio.error = ""
            envio.enviado_en = timezone.now()
            enviados += 1
        envio.save(update_fields=["estado", "intentos", "error", "id_externo", "enviado_en"])
    return enviados, fallidos


def despachar_al_confirmar():
    """Despacha en cuanto se confirme la transacción en curso (p. ej. una alerta urgente), sin esperar al programador."""
    if activo():
        transaction.on_commit(_despachar_sin_fallar)


def _despachar_sin_fallar():
    try:
        despachar()
    except Exception:  # noqa: BLE001 - el aviso ya quedó en la plataforma; el programador reintentará
        registro.exception("No se pudo despachar la cola de WhatsApp")
