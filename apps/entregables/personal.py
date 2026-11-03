"""Gestión de personal, responsables de apoyo, reasignación e identificación de conflictos (SDD del Sprint 2, RF-31, §7.6 y §8)."""
import datetime
from collections import namedtuple

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.alertas.models import Notificacion
from apps.cuentas.models import Ausencia, Usuario

from . import adjuntos
from .models import Entregable, ResponsableApoyo
from .visibilidad import es_senior_del_entregable

E = Entregable.Estado

ResultadoAsignacion = namedtuple("ResultadoAsignacion", "confirmado conflictos objeto")


def enlace_responsables(entregable):
    return reverse("entregable_detalle", args=[entregable.pk]) + "#responsables"


def puede_gestionar_responsables(usuario, entregable):
    """Gerente, admin, senior responsable del contrato o senior revisor del entregable (§7.6 y §8)."""
    return es_senior_del_entregable(usuario, entregable)


def _fecha(valor, nombre="La fecha"):
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime.date) and not isinstance(valor, datetime.datetime):
        return valor
    try:
        return datetime.date.fromisoformat(str(valor).strip())
    except ValueError:
        raise ValidationError(f"{nombre} no tiene un formato válido (AAAA-MM-DD).")


def entregables_activos_elaboracion(usuario):
    """Entregables activos (no Entregados) donde la persona es junior principal o apoyo activo."""
    return (
        Entregable.objects.exclude(estado=E.HECHO)
        .filter(
            Q(junior_asignado=usuario)
            | Q(responsables_apoyo__usuario=usuario, responsables_apoyo__activo=True)
        )
        .distinct()
    )


def entregables_activos_usuario(usuario):
    """Todos los entregables activos vinculados a la persona (junior principal, apoyo activo o senior revisor)."""
    return (
        Entregable.objects.exclude(estado=E.HECHO)
        .filter(
            Q(junior_asignado=usuario)
            | Q(senior_revisor=usuario)
            | Q(responsables_apoyo__usuario=usuario, responsables_apoyo__activo=True)
        )
        .distinct()
    )


def detectar_conflictos(usuario, entregable=None, fecha_referencia=None, hoy=None):
    """Detecta conflictos antes de confirmar una asignación o reasignación (§7.6):

    1. Sobrecarga: más de `settings.CARGA_MAXIMA_ACTIVOS` entregables activos (actualmente > tope, o al sumar este
       entregable activo superaría el tope).
    2. Plazo cercano: otro entregable activo asignado a la persona con plazo a 2 días o menos de diferencia.
    3. Ausencia: una ausencia registrada que cubre el plazo (o se cruza entre hoy y el plazo).

    Devuelve una lista de mensajes legibles (vacía si no hay conflictos). Los conflictos son un aviso, no un bloqueo.
    """
    if usuario is None or not getattr(usuario, "pk", None):
        return []
    hoy = hoy or timezone.localdate()
    tope = settings.CARGA_MAXIMA_ACTIVOS
    plazo = _fecha(fecha_referencia) if fecha_referencia is not None else (entregable.plazo if entregable is not None else None)
    conflictos = []

    # 1. Sobrecarga de entregables activos (elaboración / apoyo)
    activos_qs = entregables_activos_elaboracion(usuario)
    n_actual = activos_qs.count()
    n_otros = activos_qs.exclude(pk=entregable.pk).count() if (entregable is not None and entregable.pk) else n_actual
    entregable_activo = entregable is None or entregable.estado != E.HECHO
    if n_actual > tope or (entregable_activo and n_otros >= tope):
        conflictos.append(
            f"Sobrecarga: {usuario.nombre} tiene {n_actual} entregable{'s' if n_actual != 1 else ''} "
            f"activo{'s' if n_actual != 1 else ''} (máximo sugerido {tope})."
        )

    # 2. Otro entregable activo con plazo en los mismos 2 días
    if plazo is not None:
        delta = datetime.timedelta(days=2)
        rango = (plazo - delta, plazo + delta)
        otros_qs = entregables_activos_usuario(usuario)
        if entregable is not None and entregable.pk:
            otros_qs = otros_qs.exclude(pk=entregable.pk)
        cercanos = list(
            otros_qs.filter(
                Q(plazo__range=rango)
                | Q(
                    responsables_apoyo__usuario=usuario,
                    responsables_apoyo__activo=True,
                    responsables_apoyo__fecha_limite__range=rango,
                )
            )
            .distinct()
            .order_by("plazo", "id")
        )
        if cercanos:
            detalle = ", ".join(f"{o.referencia} ({o.plazo:%d/%m/%Y})" for o in cercanos[:3])
            conflictos.append(
                f"Plazo cercano: {usuario.nombre} tiene otro entregable con vencimiento cercano al "
                f"{plazo:%d/%m/%Y}: {detalle}."
            )

    # 3. Ausencia registrada que cubre el plazo (o entre hoy y el plazo)
    if plazo is not None:
        inicio_ventana = min(hoy, plazo)
        ausencias = list(
            Ausencia.objects.filter(usuario=usuario, desde__lte=plazo, hasta__gte=inicio_ventana).order_by("desde", "id")
        )
    else:
        ausencias = list(Ausencia.objects.filter(usuario=usuario, hasta__gte=hoy).order_by("desde", "id"))
    for a in ausencias:
        conflictos.append(
            f"Ausencia registrada: {usuario.nombre} estará ausente del {a.desde:%d/%m/%Y} al {a.hasta:%d/%m/%Y} ({a.motivo})."
        )

    return conflictos


def reasignar_principal(entregable, rol_destino, nuevo_usuario, autor, motivo="", confirmar=False, hoy=None):
    """Reasigna el `junior_asignado` o el `senior_revisor` del entregable (§7.6).

    - Solo puede hacerlo el senior del entregable (responsable del contrato o revisor), el gerente o el admin.
    - Si hay conflictos y `confirmar` es False, no guarda y devuelve `ResultadoAsignacion(False, conflictos, entregable)`.
    - Al confirmar (o sin conflictos): actualiza el responsable, deja constancia en `HistorialEstado` («Reasignado de X a Y»)
      y envía `Notificacion` de tipo `REASIGNACION` tanto a quien entra como a quien sale (salvo que coincida con el autor).
    """
    if not puede_gestionar_responsables(autor, entregable):
        raise PermissionDenied("Solo el senior del entregable, el gerente y el admin pueden reasignar responsables.")

    rol_norm = (rol_destino or "").strip().lower()
    if rol_norm in ("junior", "junior_asignado"):
        campo = "junior_asignado"
        rol_esperado = Usuario.Rol.JUNIOR
        etiqueta_rol = "junior principal"
        anterior = entregable.junior_asignado
    elif rol_norm in ("senior", "senior_revisor"):
        campo = "senior_revisor"
        rol_esperado = Usuario.Rol.SENIOR
        etiqueta_rol = "senior revisor"
        anterior = entregable.senior_revisor
    else:
        raise ValidationError("Indique si desea reasignar al junior principal o al senior revisor.")

    if isinstance(nuevo_usuario, (int, str)):
        try:
            nuevo_usuario = Usuario.objects.get(pk=int(nuevo_usuario), is_active=True)
        except (TypeError, ValueError, OverflowError, Usuario.DoesNotExist):
            nuevo_usuario = None
    if nuevo_usuario is None or not getattr(nuevo_usuario, "is_active", False) or nuevo_usuario.rol != rol_esperado:
        raise ValidationError(f"Elija un {etiqueta_rol} activo válido de la lista.")

    if nuevo_usuario.pk == anterior.pk:
        raise ValidationError(f"{nuevo_usuario.nombre} ya está asignado como {etiqueta_rol} de este entregable.")

    conflictos = detectar_conflictos(nuevo_usuario, entregable=entregable, hoy=hoy)
    if conflictos and not confirmar:
        return ResultadoAsignacion(confirmado=False, conflictos=conflictos, objeto=entregable)

    motivo_limpio = (motivo or "").strip()
    base_detalle = f"Reasignado de {anterior.nombre} a {nuevo_usuario.nombre}"
    detalle = f"{base_detalle} ({motivo_limpio})" if motivo_limpio else base_detalle

    with transaction.atomic():
        setattr(entregable, campo, nuevo_usuario)
        entregable.save(update_fields=[campo, "actualizado_en"])
        adjuntos.registrar_en_historial(entregable, autor, detalle[:255])

        enlace = enlace_responsables(entregable)
        if nuevo_usuario.pk != autor.pk:
            Notificacion.objects.create(
                usuario=nuevo_usuario,
                entregable=entregable,
                tipo=Notificacion.Tipo.REASIGNACION,
                mensaje=f"Se le asignó {entregable.referencia} (reasignado de {anterior.nombre} a {nuevo_usuario.nombre})."[:255],
                enlace=enlace,
            )
        if anterior.pk != autor.pk and anterior.pk != nuevo_usuario.pk:
            Notificacion.objects.create(
                usuario=anterior,
                entregable=entregable,
                tipo=Notificacion.Tipo.REASIGNACION,
                mensaje=f"{entregable.referencia} fue reasignado de {anterior.nombre} a {nuevo_usuario.nombre}."[:255],
                enlace=enlace,
            )

    return ResultadoAsignacion(confirmado=True, conflictos=conflictos, objeto=entregable)


def sumar_apoyo(
    entregable,
    usuario,
    funcion=ResponsableApoyo.Funcion.ELABORACION,
    autor=None,
    fecha_limite=None,
    confirmar=False,
    hoy=None,
):
    """Suma un `ResponsableApoyo` activo al entregable (§7.6).

    - Solo puede hacerlo el senior del entregable, el gerente o el admin.
    - Un usuario no repite función activa en el mismo entregable.
    - Si hay conflictos y `confirmar` es False, no guarda y devuelve los conflictos para confirmar.
    """
    if autor is None or not puede_gestionar_responsables(autor, entregable):
        raise PermissionDenied("Solo el senior del entregable, el gerente y el admin pueden sumar responsables de apoyo.")

    if isinstance(usuario, (int, str)):
        try:
            usuario = Usuario.objects.get(pk=int(usuario), is_active=True)
        except (TypeError, ValueError, OverflowError, Usuario.DoesNotExist):
            usuario = None
    if usuario is None or not getattr(usuario, "is_active", False):
        raise ValidationError("Elija un colaborador activo válido para sumar como apoyo.")

    if funcion not in ResponsableApoyo.Funcion.values:
        raise ValidationError("Elija una función válida para el responsable de apoyo.")

    limite = _fecha(fecha_limite, "La fecha límite")

    if ResponsableApoyo.objects.filter(entregable=entregable, usuario=usuario, funcion=funcion, activo=True).exists():
        etiqueta = ResponsableApoyo.Funcion(funcion).label.lower()
        raise ValidationError(f"{usuario.nombre} ya figura como apoyo ({etiqueta}) activo en este entregable.")

    conflictos = detectar_conflictos(usuario, entregable=entregable, fecha_referencia=limite or entregable.plazo, hoy=hoy)
    if conflictos and not confirmar:
        return ResultadoAsignacion(confirmado=False, conflictos=conflictos, objeto=None)

    with transaction.atomic():
        apoyo = ResponsableApoyo.objects.create(
            entregable=entregable,
            usuario=usuario,
            funcion=funcion,
            fecha_limite=limite,
            asignado_por=autor,
            activo=True,
        )
        etiqueta = apoyo.get_funcion_display().lower()
        adjuntos.registrar_en_historial(
            entregable, autor, f"Sumó a {usuario.nombre} como apoyo ({etiqueta})"
        )
        if usuario.pk != autor.pk:
            Notificacion.objects.create(
                usuario=usuario,
                entregable=entregable,
                tipo=Notificacion.Tipo.REASIGNACION,
                mensaje=f"Se le sumó como apoyo ({etiqueta}) en {entregable.referencia}."[:255],
                enlace=enlace_responsables(entregable),
            )

    return ResultadoAsignacion(confirmado=True, conflictos=conflictos, objeto=apoyo)


def quitar_apoyo(apoyo, autor):
    """Da de baja lógica (`activo=False`) a un responsable de apoyo y lo registra en el historial."""
    entregable = apoyo.entregable
    if not puede_gestionar_responsables(autor, entregable):
        raise PermissionDenied("Solo el senior del entregable, el gerente y el admin pueden quitar responsables de apoyo.")
    if not apoyo.activo:
        raise ValidationError("Ese responsable de apoyo ya fue quitado.")

    etiqueta = apoyo.get_funcion_display().lower()
    with transaction.atomic():
        apoyo.activo = False
        apoyo.save(update_fields=["activo"])
        adjuntos.registrar_en_historial(
            entregable, autor, f"Quitó a {apoyo.usuario.nombre} como apoyo ({etiqueta})"
        )
        if apoyo.usuario_id != autor.pk:
            Notificacion.objects.create(
                usuario=apoyo.usuario,
                entregable=entregable,
                tipo=Notificacion.Tipo.REASIGNACION,
                mensaje=f"Ya no figura como apoyo ({etiqueta}) en {entregable.referencia}."[:255],
                enlace=enlace_responsables(entregable),
            )
    return apoyo


def registrar_ausencia(usuario, desde, hasta, motivo, autor):
    """Registra una ausencia para un colaborador (solo gerente y admin)."""
    if not getattr(autor, "es_gerente_o_admin", False):
        raise PermissionDenied("Solo el gerente y el admin registran ausencias.")
    if isinstance(usuario, (int, str)):
        try:
            usuario = Usuario.objects.get(pk=int(usuario), is_active=True)
        except (TypeError, ValueError, OverflowError, Usuario.DoesNotExist):
            usuario = None
    if usuario is None or not getattr(usuario, "is_active", False):
        raise ValidationError("Elija un colaborador válido.")
    fecha_desde = _fecha(desde, "La fecha de inicio")
    fecha_hasta = _fecha(hasta, "La fecha de fin")
    if fecha_desde is None:
        raise ValidationError("Indique la fecha de inicio de la ausencia.")
    if fecha_hasta is None:
        raise ValidationError("Indique la fecha de fin de la ausencia.")
    if fecha_hasta < fecha_desde:
        raise ValidationError("La fecha de fin no puede ser anterior a la fecha de inicio.")
    motivo_limpio = (motivo or "").strip()
    if not motivo_limpio:
        raise ValidationError("Indique el motivo de la ausencia.")
    return Ausencia.objects.create(
        usuario=usuario,
        desde=fecha_desde,
        hasta=fecha_hasta,
        motivo=motivo_limpio[:200],
        registrada_por=autor,
    )


def resumen_colaboradores(rol=None, q="", hoy=None):
    """Listado de colaboradores con su carga, entregables que vencen en 7 días y ausencias próximas (s2-personal.html)."""
    hoy = hoy or timezone.localdate()
    limite_7 = hoy + datetime.timedelta(days=7)
    tope = settings.CARGA_MAXIMA_ACTIVOS

    qs = Usuario.objects.filter(is_active=True)
    if rol in Usuario.Rol.values:
        qs = qs.filter(rol=rol)
    texto = (q or "").strip()
    if texto:
        qs = qs.filter(
            Q(first_name__icontains=texto)
            | Q(last_name__icontains=texto)
            | Q(username__icontains=texto)
            | Q(puesto__icontains=texto)
        )

    orden_rol = {
        Usuario.Rol.JUNIOR: 0,
        Usuario.Rol.SENIOR: 1,
        Usuario.Rol.GERENTE: 2,
        Usuario.Rol.ADMIN: 3,
    }
    usuarios = sorted(qs, key=lambda u: (orden_rol.get(u.rol, 9), u.nombre.lower(), u.pk))

    ausencias_por_usuario = {}
    for a in Ausencia.objects.filter(usuario__in=usuarios, hasta__gte=hoy).order_by("desde", "id"):
        ausencias_por_usuario.setdefault(a.usuario_id, []).append(a)

    filas = []
    for u in usuarios:
        if u.es_senior:
            activos_qs = entregables_activos_usuario(u)
            revisa_qs = Entregable.objects.exclude(estado=E.HECHO).filter(senior_revisor=u)
            n_activos = activos_qs.count()
            n_revisa = revisa_qs.count()
            n_elabora = entregables_activos_elaboracion(u).count()
            vencen_7 = activos_qs.filter(plazo__gte=hoy, plazo__lte=limite_7).count()
            sobrecarga = n_elabora > tope
            porcentaje = min(100, round(100 * n_activos / tope)) if tope else 0
        else:
            activos_qs = entregables_activos_elaboracion(u)
            n_activos = activos_qs.count()
            n_revisa = 0
            n_elabora = n_activos
            vencen_7 = activos_qs.filter(plazo__gte=hoy, plazo__lte=limite_7).count()
            sobrecarga = n_activos > tope
            porcentaje = min(100, round(100 * n_activos / tope)) if tope else 0

        filas.append({
            "usuario": u,
            "activos": n_activos,
            "revisa": n_revisa,
            "elabora": n_elabora,
            "vencen_7": vencen_7,
            "ausencias": ausencias_por_usuario.get(u.pk, []),
            "sobrecarga": sobrecarga,
            "porcentaje": porcentaje,
            "tope": tope,
        })
    return filas


def asignaciones_de(usuario):
    """Asignaciones activas (entregables no cerrados) de un colaborador para la pantalla `/personal/`."""
    if usuario is None:
        return []
    salida = []
    for e in (
        Entregable.objects.exclude(estado=E.HECHO)
        .filter(junior_asignado=usuario)
        .select_related("contrato__cliente")
        .order_by("plazo", "id")
    ):
        salida.append({
            "entregable": e,
            "funcion": "Junior principal",
            "tipo": "junior",
            "plazo": e.plazo,
            "apoyo": None,
        })
    for e in (
        Entregable.objects.exclude(estado=E.HECHO)
        .filter(senior_revisor=usuario)
        .select_related("contrato__cliente")
        .order_by("plazo", "id")
    ):
        salida.append({
            "entregable": e,
            "funcion": "Senior revisor",
            "tipo": "senior",
            "plazo": e.plazo,
            "apoyo": None,
        })
    for ap in (
        ResponsableApoyo.objects.filter(usuario=usuario, activo=True)
        .exclude(entregable__estado=E.HECHO)
        .select_related("entregable__contrato__cliente")
        .order_by("entregable__plazo", "id")
    ):
        salida.append({
            "entregable": ap.entregable,
            "funcion": f"Apoyo ({ap.get_funcion_display().lower()})",
            "tipo": "apoyo",
            "plazo": ap.fecha_limite or ap.entregable.plazo,
            "apoyo": ap,
        })
    return salida
