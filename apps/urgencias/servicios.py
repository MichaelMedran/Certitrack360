"""Reglas de la alerta de urgencia fuera de horario (SDD del Sprint 3, RF-43, HU-28, §7.4 y §8). Las vistas solo llaman aquí."""
import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.alertas import whatsapp
from apps.alertas.models import Notificacion
from apps.cuentas.models import Usuario
from apps.entregables.models import Entregable, HistorialEstado
from apps.entregables.visibilidad import entregables_visibles, es_senior_del_entregable

from .models import AlertaUrgente, LecturaAlerta

E = Entregable.Estado
registro = logging.getLogger(__name__)

MAX_NATURALEZA = 1000


# ------------------------------------------------------------------ permisos

def puede_activar(usuario, entregable):
    """Senior del entregable (responsable del contrato o revisor), gerente y admin. El junior no."""
    return bool(usuario.is_authenticated and es_senior_del_entregable(usuario, entregable))


def es_destinatario(usuario, alerta):
    return alerta.destinatarios.filter(pk=usuario.pk).exists()


def puede_responder(usuario, alerta):
    """Confirmar lectura o aceptar el caso: un destinatario, o un senior del entregable (gerente y admin incluidos)."""
    if not usuario.is_authenticated:
        return False
    return es_destinatario(usuario, alerta) or es_senior_del_entregable(usuario, alerta.entregable)


def exigir(permitido, mensaje="No tiene permiso para esa acción con la alerta urgente."):
    if not permitido:
        raise PermissionDenied(mensaje)


def marcar_guardia(actor, objetivo, de_guardia):
    """Marca o quita «de guardia» (D4: sin rol nuevo). Solo gerente y admin; solo se marca a quien está activo."""
    exigir(actor.is_authenticated and actor.es_gerente_o_admin, "Solo el gerente o el admin marcan la guardia.")
    if de_guardia and not objetivo.is_active:
        raise ValidationError("No se puede marcar de guardia a una persona inactiva.")
    objetivo.de_guardia = bool(de_guardia)
    objetivo.save(update_fields=["de_guardia"])
    return objetivo


# ------------------------------------------------------------------ lo que lee el resto del sistema (S3-H3, tarjetas)

def abierta_de(entregable):
    """La alerta sin cerrar del entregable, o None."""
    return AlertaUrgente.objects.abiertas().filter(entregable=entregable).first()


def ids_con_alerta_abierta(entregables=None):
    """Conjunto de ids de entregable con alerta abierta. `entregables`: iterable de ids o de entregables (None: todos).

    Es una sola consulta, para calcular la prioridad de varias filas sin consultar una por una.
    """
    qs = AlertaUrgente.objects.abiertas()
    if entregables is not None:
        qs = qs.filter(entregable_id__in=[getattr(e, "pk", e) for e in entregables])
    return set(qs.values_list("entregable_id", flat=True))


def condicion_alerta_abierta():
    """Condición (`Q`) sobre `Entregable`: tiene una alerta urgente abierta. Sirve para filtrar y ordenar con subconsulta."""
    return Q(pk__in=AlertaUrgente.objects.abiertas().values("entregable_id"))


def enriquecer(entregables, usuario=None):
    """Deja `e.alerta_urgente_abierta` (bool) en cada tarjeta o fila con una consulta por lote."""
    entregables = entregables if isinstance(entregables, list) else list(entregables)
    con_alerta = ids_con_alerta_abierta(entregables) if entregables else set()
    for e in entregables:
        e.alerta_urgente_abierta = e.pk in con_alerta
    return entregables


# ------------------------------------------------------------------ horario

def esta_fuera_de_horario(momento):
    """True si `momento` cae fuera del horario laboral (`HORARIO_LABORAL`, hora de Lima): fin de semana o fuera de las horas."""
    dias, inicio, fin = settings.HORARIO_LABORAL
    local = timezone.localtime(momento)
    return not (local.isoweekday() in dias and inicio <= local.time() < fin)


# ------------------------------------------------------------------ activar

def destinatarios_de(entregable, activador=None):
    """Guardia activa, senior responsable del contrato, senior revisor y junior asignado: sin repetir y sin quien activa."""
    candidatos = list(Usuario.objects.filter(de_guardia=True, is_active=True))
    candidatos += [entregable.contrato.senior_responsable, entregable.senior_revisor, entregable.junior_asignado]
    vistos, salida = set(), []
    for u in candidatos:
        if u is None or not u.is_active or u.pk in vistos or (activador is not None and u.pk == activador.pk):
            continue
        vistos.add(u.pk)
        salida.append(u)
    return salida


def texto_aviso(alerta):
    """«URGENTE · cliente · naturaleza · plazo esperado …» (cabe en el aviso, de 255 caracteres)."""
    plazo = timezone.localtime(alerta.plazo_esperado).strftime("%d/%m/%Y %H:%M")
    cliente = alerta.entregable.contrato.cliente.nombre
    cola = f" · plazo esperado {plazo}"
    cabeza = f"URGENTE · {cliente} · "
    naturaleza = " ".join(alerta.naturaleza.split())
    disponible = 255 - len(cabeza) - len(cola)
    if len(naturaleza) > disponible:
        naturaleza = naturaleza[: max(disponible - 1, 0)].rstrip() + "…"
    return cabeza + naturaleza + cola


def _historial(entregable, usuario, detalle):
    HistorialEstado.objects.create(
        entregable=entregable, estado_anterior=entregable.estado, estado_nuevo=entregable.estado, usuario=usuario,
        detalle=detalle[:255],
    )


def _enviar_correo(alerta, usuarios):
    """Correo «URGENTE: …» solo si hay un servidor LOCAL configurado (D3). Un fallo no deshace ni impide la alerta."""
    if not settings.EMAIL_HOST:
        return
    direcciones = [u.email for u in usuarios if u.email]
    if not direcciones:
        return
    try:
        send_mail(
            f"URGENTE: {alerta.entregable.contrato.cliente.nombre} · {alerta.entregable.codigo}",
            texto_aviso(alerta) + "\n\nEntregable: " + alerta.entregable.titulo
            + "\nIngrese a CertiTrack 360 para confirmar la lectura o aceptar el caso.",
            None, direcciones, fail_silently=False,
        )
    except Exception:  # noqa: BLE001 - cualquier fallo de red o de configuración: la alerta ya quedó registrada
        registro.exception("No se pudo enviar el correo de la alerta urgente %s", alerta.pk)


def validar_datos(naturaleza, plazo_esperado, ahora=None):
    """(naturaleza limpia, plazo): naturaleza obligatoria y plazo esperado futuro. Lanza ValidationError con el motivo."""
    ahora = ahora or timezone.now()
    naturaleza = (naturaleza or "").strip()
    errores = []
    if not naturaleza:
        errores.append("Falta la naturaleza de la urgencia.")
    elif len(naturaleza) > MAX_NATURALEZA:
        errores.append(f"La naturaleza de la urgencia admite hasta {MAX_NATURALEZA} caracteres.")
    if plazo_esperado is None:
        errores.append("Falta el plazo esperado (fecha y hora).")
    elif plazo_esperado <= ahora:
        errores.append("El plazo esperado debe ser una fecha y hora futuras.")
    if errores:
        raise ValidationError(errores)
    return naturaleza, plazo_esperado


@transaction.atomic
def activar(usuario, entregable, naturaleza, plazo_esperado, ahora=None):
    """Activa la alerta: la crea, avisa «URGENTE» a cada destinatario (una sola vez) y la deja en el historial."""
    exigir(puede_activar(usuario, entregable), "Solo el senior del entregable, el gerente o el admin activan una alerta urgente.")
    ahora = ahora or timezone.now()
    naturaleza, plazo_esperado = validar_datos(naturaleza, plazo_esperado, ahora)
    if entregable.estado == E.HECHO:
        raise ValidationError("Un entregable ya entregado no admite una alerta urgente.")
    if AlertaUrgente.objects.abiertas().filter(entregable=entregable).exists():
        raise ValidationError("Este entregable ya tiene una alerta urgente abierta.")
    try:
        with transaction.atomic():
            alerta = AlertaUrgente.objects.create(
                entregable=entregable, naturaleza=naturaleza, plazo_esperado=plazo_esperado,
                fuera_de_horario=esta_fuera_de_horario(ahora), activada_por=usuario,
            )
    except IntegrityError:  # dos activaciones a la vez: gana la primera
        raise ValidationError("Este entregable ya tiene una alerta urgente abierta.")
    usuarios = destinatarios_de(entregable, usuario)
    alerta.destinatarios.set(usuarios)
    mensaje = texto_aviso(alerta)
    # Quien está de guardia sin ser responsable no ve el entregable (404): su «Ver» lleva al inicio, donde está la franja.
    quienes_lo_ven = {u.pk for u in usuarios if entregables_visibles(u).filter(pk=entregable.pk).exists()}
    Notificacion.objects.bulk_create([
        Notificacion(
            usuario=u, entregable=entregable, tipo=Notificacion.Tipo.URGENTE, mensaje=mensaje,
            enlace="" if u.pk in quienes_lo_ven else "/",
        )
        for u in usuarios
    ])
    _historial(entregable, usuario, "Activó la alerta urgente" + (" (fuera de horario)" if alerta.fuera_de_horario else ""))
    transaction.on_commit(lambda: _enviar_correo(alerta, usuarios))
    whatsapp.despachar_al_confirmar()  # la alerta urgente no espera al programador
    return alerta


# ------------------------------------------------------------------ leer y aceptar

def confirmar_lectura(usuario, alerta):
    """Registra quién y cuándo leyó (una sola vez por persona). Devuelve la lectura."""
    exigir(puede_responder(usuario, alerta))
    lectura, _ = LecturaAlerta.objects.get_or_create(alerta=alerta, usuario=usuario)
    return lectura


@transaction.atomic
def aceptar(usuario, alerta, ahora=None):
    """«Aceptar el caso»: registra quién atiende la contingencia. Solo una persona lo acepta; al aceptarla se cierra."""
    exigir(puede_responder(usuario, alerta))
    ahora = ahora or timezone.now()
    # Actualización condicionada: si dos personas aceptan a la vez, solo una cambia la fila.
    cambiadas = AlertaUrgente.objects.filter(
        pk=alerta.pk, aceptada_por__isnull=True, cerrada_en__isnull=True,
    ).update(aceptada_por=usuario, aceptada_en=ahora, cerrada_en=ahora)
    if not cambiadas:
        alerta.refresh_from_db()
        if alerta.aceptada_por_id:
            raise ValidationError(f"El caso ya fue aceptado por {alerta.aceptada_por.nombre}.")
        raise ValidationError("La alerta ya está cerrada.")
    alerta.refresh_from_db()
    LecturaAlerta.objects.get_or_create(alerta=alerta, usuario=usuario)  # quien acepta, por fuerza leyó
    _historial(alerta.entregable, usuario, "Aceptó el caso de la alerta urgente")
    return alerta


def cerrar_al_entregar(entregable, ahora=None):
    """La alerta se cierra cuando el entregable pasa a Entregado. Devuelve cuántas cerró."""
    return AlertaUrgente.objects.abiertas().filter(entregable=entregable).update(cerrada_en=ahora or timezone.now())


def al_mover(entregable, anterior, nuevo, usuario, opciones):
    """Extensión `registrar_al_mover`: al pasar a Entregado se cierra la alerta abierta."""
    if nuevo == E.HECHO:
        cerrar_al_entregar(entregable)


# ------------------------------------------------------------------ lo que se muestra

def resumen(alerta):
    """Datos para el detalle: destinatarios, quiénes ya leyeron y quiénes faltan."""
    destinatarios = list(alerta.destinatarios.order_by("first_name", "last_name", "username"))
    leyeron = {l.usuario_id: l for l in alerta.lecturas.select_related("usuario")}
    return {
        "destinatarios": len(destinatarios),
        "leyeron": [leyeron[u.pk] for u in destinatarios if u.pk in leyeron],
        "pendientes": [u for u in destinatarios if u.pk not in leyeron],
    }


def pendientes_de_lectura(usuario):
    """Alertas abiertas que `usuario` recibió y todavía no confirmó, de la más nueva a la más antigua."""
    return list(
        AlertaUrgente.objects.abiertas()
        .filter(destinatarios=usuario).exclude(lecturas__usuario=usuario)
        .select_related("entregable", "entregable__contrato", "entregable__contrato__cliente").distinct()
    )


def enlace_detalle(alerta):
    return reverse("entregable_detalle", args=[alerta.entregable_id])
