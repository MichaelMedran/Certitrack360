"""Servicio de registro de tiempo por etapa (SDD del Sprint 2, RF-32, §6.2, §7.7 y §8)."""
import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import RegistroTiempo
from .visibilidad import entregables_visibles, es_responsable_activo

MAX_BLOQUE_MANUAL = datetime.timedelta(hours=12)


def enlace_tiempo(entregable):
    return reverse("entregable_detalle", args=[entregable.pk]) + "#tiempo"


def formatear_segundos(segundos):
    """Convierte segundos a texto 'X h YY min' (redondeado al minuto)."""
    total_min = max(0, round(segundos / 60))
    horas, minutos = divmod(total_min, 60)
    return f"{horas} h {minutos:02d} min"


def puede_registrar_tiempo(usuario, entregable):
    """Junior asignado, responsable de apoyo activo, senior del entregable, gerente o admin (§7.7 y §8)."""
    return es_responsable_activo(usuario, entregable)


def visibles(usuario):
    """Registros de tiempo visibles en `/tiempos/` según el rol (§7.7 y §8):
    - Junior: solo sus propios registros (en entregables visibles).
    - Senior: los de sus entregables visibles.
    - Gerente y Admin: todos.
    """
    if not getattr(usuario, "is_authenticated", False):
        return RegistroTiempo.objects.none()
    if usuario.es_junior:
        return RegistroTiempo.objects.filter(usuario=usuario, entregable__in=entregables_visibles(usuario))
    if usuario.es_senior:
        return RegistroTiempo.objects.filter(entregable__in=entregables_visibles(usuario))
    return RegistroTiempo.objects.all()


def _fecha_hora(valor, nombre="La fecha y hora"):
    if valor in (None, ""):
        raise ValidationError(f"Indique {nombre.lower()}.")
    if isinstance(valor, datetime.datetime):
        dt = valor
    elif isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            raise ValidationError(f"Indique {nombre.lower()}.")
        dt = None
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"):
            try:
                dt = datetime.datetime.strptime(texto, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            try:
                dt = datetime.datetime.fromisoformat(texto)
            except ValueError:
                raise ValidationError(f"{nombre} no tiene un formato válido (AAAA-MM-DD HH:MM).")
    else:
        raise ValidationError(f"{nombre} no tiene un formato válido.")

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def iniciar(entregable, usuario, etapa, ahora=None):
    """Inicia un tramo en la etapa indicada para `usuario` en `entregable` (§7.7).

    Si el usuario tenía otro registro abierto (en este u otro entregable), lo pausa en la misma transacción
    (`fin = ahora`) antes de abrir el nuevo, garantizando que nunca haya dos registros abiertos.
    Devuelve `(nuevo_registro, registro_pausado_o_None)`.
    """
    if not puede_registrar_tiempo(usuario, entregable):
        raise PermissionDenied("Solo los responsables del entregable pueden registrar tiempo.")
    if etapa not in RegistroTiempo.Etapa.values:
        raise ValidationError("Elija una etapa válida (Recopilación, Consolidación o Revisión).")

    ahora = ahora or timezone.now()
    with transaction.atomic():
        abiertos = list(
            RegistroTiempo.objects.select_for_update()
            .filter(usuario=usuario, fin__isnull=True)
            .select_related("entregable")
        )
        pausado = None
        for ab in abiertos:
            ab.fin = max(ahora, ab.inicio)
            ab.save(update_fields=["fin"])
            pausado = ab

        nuevo = RegistroTiempo.objects.create(
            entregable=entregable,
            usuario=usuario,
            etapa=etapa,
            inicio=ahora,
        )
    return nuevo, pausado


def pausar(entregable, usuario, ahora=None):
    """Pausa el registro de tiempo abierto de `usuario` en `entregable`."""
    if not puede_registrar_tiempo(usuario, entregable):
        raise PermissionDenied("Solo los responsables del entregable pueden pausar tiempo.")

    ahora = ahora or timezone.now()
    with transaction.atomic():
        abierto = (
            RegistroTiempo.objects.select_for_update()
            .filter(entregable=entregable, usuario=usuario, fin__isnull=True)
            .first()
        )
        if abierto is None:
            raise ValidationError("No tiene un registro de tiempo en curso en este entregable.")
        abierto.fin = max(ahora, abierto.inicio)
        abierto.save(update_fields=["fin"])
    return abierto


def finalizar_etapa(entregable, usuario, etapa=None, ahora=None):
    """Marca el cierre de una etapa (`cierra_etapa=True`) en `entregable`.

    Si el usuario tiene un registro abierto en el entregable (de esa etapa, o cualquiera si no se indicó etapa),
    lo cierra con `fin = ahora` y `cierra_etapa = True`. Si no hay uno abierto, marca el último tramo de la etapa
    indicada como `cierra_etapa = True` (o crea un cierre de duración cero si la etapa aún no tenía tramos).
    """
    if not puede_registrar_tiempo(usuario, entregable):
        raise PermissionDenied("Solo los responsables del entregable pueden finalizar una etapa.")

    ahora = ahora or timezone.now()
    with transaction.atomic():
        qs_abierto = RegistroTiempo.objects.select_for_update().filter(
            entregable=entregable, usuario=usuario, fin__isnull=True
        )
        if etapa in RegistroTiempo.Etapa.values:
            abierto = qs_abierto.filter(etapa=etapa).first() or qs_abierto.first()
        else:
            abierto = qs_abierto.first()

        if abierto is not None:
            abierto.fin = max(ahora, abierto.inicio)
            abierto.cierra_etapa = True
            abierto.save(update_fields=["fin", "cierra_etapa"])
            return abierto

        if etapa not in RegistroTiempo.Etapa.values:
            raise ValidationError("Elija una etapa válida para finalizar.")

        ultimo = (
            RegistroTiempo.objects.select_for_update()
            .filter(entregable=entregable, etapa=etapa)
            .order_by("-inicio", "-id")
            .first()
        )
        if ultimo is not None:
            ultimo.cierra_etapa = True
            ultimo.save(update_fields=["cierra_etapa"])
            return ultimo

        return RegistroTiempo.objects.create(
            entregable=entregable,
            usuario=usuario,
            etapa=etapa,
            inicio=ahora,
            fin=ahora,
            cierra_etapa=True,
        )


def registrar_manual(entregable, usuario, etapa, inicio, fin, motivo, cierra_etapa=False, ahora=None):
    """Registra un bloque de tiempo manual con motivo obligatorio (§7.7):
    - `fin > inicio`
    - sin tiempos futuros (`fin <= ahora`)
    - máximo 12 h por bloque (`fin - inicio <= 12 h`)
    - `motivo` no vacío
    """
    if not puede_registrar_tiempo(usuario, entregable):
        raise PermissionDenied("Solo los responsables del entregable pueden registrar ajustes manuales de tiempo.")
    if etapa not in RegistroTiempo.Etapa.values:
        raise ValidationError("Elija una etapa válida (Recopilación, Consolidación o Revisión).")

    motivo_limpio = (motivo or "").strip()
    if not motivo_limpio:
        raise ValidationError("Indique el motivo del ajuste manual.")

    dt_inicio = _fecha_hora(inicio, "La fecha y hora de inicio")
    dt_fin = _fecha_hora(fin, "La fecha y hora de fin")
    ahora = ahora or timezone.now()

    if dt_fin <= dt_inicio:
        raise ValidationError("La fecha y hora de fin debe ser posterior a la de inicio.")
    if dt_fin > ahora:
        raise ValidationError("No se puede registrar tiempo en el futuro.")
    if (dt_fin - dt_inicio) > MAX_BLOQUE_MANUAL:
        raise ValidationError("Un bloque manual no puede superar las 12 horas.")

    return RegistroTiempo.objects.create(
        entregable=entregable,
        usuario=usuario,
        etapa=etapa,
        inicio=dt_inicio,
        fin=dt_fin,
        cierra_etapa=bool(cierra_etapa),
        manual=True,
        motivo=motivo_limpio[:255],
    )


def resumen_tiempos(entregable, usuario=None, ahora=None):
    """Resumen de tiempos por etapa y tramos registrados para la ficha del entregable (`s2-entregable.html`)."""
    ahora = ahora or timezone.now()
    registros = list(
        entregable.registros_tiempo.select_related("usuario").order_by("-inicio", "-id")
    )

    por_etapa = {codigo: [] for codigo in RegistroTiempo.Etapa.values}
    for r in registros:
        r.duracion_calculada = formatear_segundos(r.segundos(ahora=ahora))
        if r.etapa in por_etapa:
            por_etapa[r.etapa].append(r)

    etapas = []
    total_segundos = 0
    for codigo, etiqueta in RegistroTiempo.Etapa.choices:
        lista = por_etapa[codigo]
        seg = sum(r.segundos(ahora=ahora) for r in lista)
        total_segundos += seg
        if any(r.abierto for r in lista):
            estado = "En curso"
        elif any(r.cierra_etapa for r in lista):
            estado = "Finalizada"
        elif lista:
            estado = "En curso"
        else:
            estado = "Sin iniciar"
        etapas.append({
            "codigo": codigo,
            "etiqueta": etiqueta,
            "estado": estado,
            "segundos": seg,
            "duracion_texto": formatear_segundos(seg),
        })

    abierto_entregable = None
    abierto_otro = None
    if usuario is not None and getattr(usuario, "is_authenticated", False):
        abierto = (
            RegistroTiempo.objects.filter(usuario=usuario, fin__isnull=True)
            .select_related("entregable")
            .first()
        )
        if abierto is not None:
            abierto.duracion_calculada = formatear_segundos(abierto.segundos(ahora=ahora))
            if abierto.entregable_id == entregable.pk:
                abierto_entregable = abierto
            else:
                abierto_otro = abierto

    etapa_sugerida = (
        abierto_entregable.etapa
        if abierto_entregable is not None
        else next(
            (e["codigo"] for e in etapas if e["estado"] != "Finalizada"),
            RegistroTiempo.Etapa.RECOPILACION,
        )
    )

    return {
        "etapas": etapas,
        "total_segundos": total_segundos,
        "total_texto": formatear_segundos(total_segundos),
        "registros": registros,
        "abierto_entregable": abierto_entregable,
        "abierto_otro": abierto_otro,
        "etapa_sugerida": etapa_sugerida,
    }
