"""Verificación del número de factura (SDD del Sprint 3, RF-46 y §7.7; HU-30).

Los responsables activos ingresan el número y el conector lo consulta en solo lectura. Si el entregable tiene número de
factura, para aprobarlo (Revisión senior → Aprobado) su última verificación debe ser correcta o tener la justificación de
un senior del entregable. Un entregable sin número no exige nada (D7). Cada verificación y cada justificación quedan en
el historial del entregable.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.alertas.models import Notificacion
from apps.entregables import adjuntos
from apps.entregables.models import Entregable
from apps.entregables.visibilidad import es_responsable_activo, es_senior_del_entregable

from .conector import ErrorConexion, obtener_conector
from .models import FacturaSimulada, VerificacionFactura

E = Entregable.Estado
R = VerificacionFactura.Resultado
NUMERO_MAX = VerificacionFactura._meta.get_field("numero").max_length


def enlace(entregable):
    return reverse("entregable_detalle", args=[entregable.pk]) + "#factura"


def puede_verificar(usuario, entregable):
    """Los responsables activos (junior, apoyos y seniors del entregable; gerente y admin). Un entregado ya no cambia."""
    return entregable.estado != E.HECHO and es_responsable_activo(usuario, entregable)


def puede_justificar(usuario, entregable):
    """Solo el senior del entregable, el gerente o el admin."""
    return entregable.estado != E.HECHO and es_senior_del_entregable(usuario, entregable)


def vigente(entregable):
    """La última verificación del entregable (su número de factura vigente), o None si nunca se verificó."""
    return entregable.verificaciones_factura.order_by("-fecha", "-id").first()


def motivo(resultado, numero, factura, entregable):
    """Texto exacto que se muestra al usuario para un resultado de la consulta."""
    cliente, contrato = entregable.contrato.cliente.nombre, entregable.contrato.numero_contrato
    if resultado == R.CORRECTA:
        return f"La factura {numero} existe, no está anulada y coincide con el cliente y el contrato del entregable."
    if resultado == R.NO_EXISTE:
        return f"La factura {numero} no existe en la base de facturación."
    if resultado == R.OTRO_CLIENTE:
        return f"La factura {numero} existe, pero pertenece a {factura['cliente']}, no a {cliente}."
    if resultado == R.OTRO_CONTRATO:
        return f"La factura {numero} existe, pero corresponde al contrato {factura['contrato']}, no al {contrato}."
    if resultado == R.ANULADA:
        return f"La factura {numero} está anulada."
    return f"No se pudo consultar la facturación para verificar la factura {numero}. Intente de nuevo más tarde."


def evaluar(entregable, factura):
    """Resultado de comparar la respuesta del conector (o None si el número no existe) con el entregable."""
    if factura is None:
        return R.NO_EXISTE
    contrato = entregable.contrato
    if (factura.get("cliente") or "").strip().casefold() != contrato.cliente.nombre.strip().casefold():
        return R.OTRO_CLIENTE
    if (factura.get("contrato") or "").strip().casefold() != contrato.numero_contrato.strip().casefold():
        return R.OTRO_CONTRATO
    if factura.get("estado") == FacturaSimulada.Estado.ANULADA:
        return R.ANULADA
    return R.CORRECTA


def verificar(entregable, usuario, numero, conector=None):
    """Consulta el número de factura (solo lectura) y guarda la verificación. Devuelve la `VerificacionFactura`."""
    if not es_responsable_activo(usuario, entregable):
        raise PermissionDenied("Solo los responsables del entregable verifican su factura.")
    if entregable.estado == E.HECHO:
        raise ValidationError(f"La factura de un entregable «{E.HECHO.label}» ya no se verifica.")
    numero = " ".join((numero or "").split())
    if not numero:
        raise ValidationError("Ingrese el número de factura o el correlativo.")
    if len(numero) > NUMERO_MAX:
        raise ValidationError(f"El número de factura es demasiado largo (máximo {NUMERO_MAX} caracteres).")
    try:
        factura = (conector or obtener_conector()).consultar(numero)
    except ErrorConexion:
        resultado, factura = R.SIN_CONEXION, None
    except Exception:  # noqa: BLE001 - un conector real puede fallar de muchas formas; la causa no debe tumbar la pantalla
        resultado, factura = R.SIN_CONEXION, None
    else:
        resultado = evaluar(entregable, factura)
    with transaction.atomic():
        verificacion = VerificacionFactura.objects.create(
            entregable=entregable, numero=numero, resultado=resultado, usuario=usuario,
            detalle={**(factura or {}), "mensaje": motivo(resultado, numero, factura, entregable)},
        )
        adjuntos.registrar_en_historial(
            entregable, usuario, f"Verificó la factura {numero}: {resultado.label}"
        )
        if resultado != R.CORRECTA:
            _avisar_al_senior(entregable, usuario, verificacion)
    return verificacion


def justificar(entregable, usuario, texto):
    """Registra la justificación del senior sobre la verificación vigente no correcta. Devuelve la verificación."""
    if not es_senior_del_entregable(usuario, entregable):
        raise PermissionDenied("Solo el senior del entregable, el gerente o el admin justifican una factura observada.")
    if entregable.estado == E.HECHO:
        raise ValidationError(f"La factura de un entregable «{E.HECHO.label}» ya no se justifica.")
    texto = (texto or "").strip()
    if not texto:
        raise ValidationError("Escriba la justificación: es obligatoria.")
    with transaction.atomic():
        verificacion = vigente(entregable)
        if verificacion is None or verificacion.correcta:
            raise ValidationError("No hay una verificación observada que justificar.")
        if verificacion.justificada:
            raise ValidationError("La verificación vigente ya tiene justificación.")
        verificacion.justificacion, verificacion.justificada_por = texto, usuario
        verificacion.justificada_en = timezone.now()
        verificacion.save(update_fields=["justificacion", "justificada_por", "justificada_en"])
        adjuntos.registrar_en_historial(
            entregable, usuario,
            f"Justificó la factura {verificacion.numero} ({verificacion.get_resultado_display()}): {texto}",
        )
    return verificacion


def _avisar_al_senior(entregable, usuario, verificacion):
    """Avisa al senior revisor cuando otra persona verifica un número observado (tipo FACTURA)."""
    destino = entregable.senior_revisor
    if destino is None or destino.pk == usuario.pk or not destino.is_active:
        return
    Notificacion.objects.create(
        usuario=destino, entregable=entregable, tipo=Notificacion.Tipo.FACTURA,
        mensaje=f"{entregable.codigo or entregable.titulo}: la factura {verificacion.numero} quedó "
                f"«{verificacion.get_resultado_display()}».",
    )


# ------------------------------------------------------------------ extensiones (§5.1)

def condicion(entregable, nuevo_estado, usuario, opciones):
    """Para aprobar, si el entregable tiene número de factura, su última verificación debe ser correcta o estar justificada
    por un senior (HU-30 criterio 3). Sin número no se exige nada."""
    if nuevo_estado != E.LISTO_PARA_ENTREGA or entregable.estado != E.VERIFICACION_SENIOR:
        return None
    ultima = vigente(entregable)
    if ultima is None or ultima.correcta or ultima.justificada:
        return None
    return (
        f"No se puede aprobar: la factura {ultima.numero} quedó «{ultima.get_resultado_display()}». Verifique un número "
        f"correcto o pida a un senior del entregable que lo justifique en la sección «Factura»."
    )


def seccion(usuario, entregable):
    """Sección «Factura» del detalle: verificar, justificar y el historial de verificaciones."""
    verificaciones = list(entregable.verificaciones_factura.select_related("usuario", "justificada_por"))
    puede = puede_verificar(usuario, entregable)
    if not verificaciones and not puede:
        return None
    ultima = verificaciones[0] if verificaciones else None
    return {
        "plantilla": "facturacion/_factura.html", "orden": 40,
        "contexto": {
            "verificaciones": verificaciones, "vigente": ultima, "puede": puede,
            "puede_justificar": puede_justificar(usuario, entregable) and ultima is not None
            and not ultima.correcta and not ultima.justificada,
            "mensaje": (ultima.detalle or {}).get("mensaje", "") if ultima else "",
        },
    }
