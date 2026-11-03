import datetime

from django.conf import settings
from django.utils import timezone

from apps.entregables.models import Entregable

from .models import Notificacion


def texto_vencimiento(entregable, dias):
    """Aviso con el código del entregable (SDD del Sprint 2, RF-20 y RF-22): hoy, mañana (24 h) o en N días."""
    if dias == 0:
        cuando = "vence hoy"
    elif dias == 1:
        cuando = f"vence mañana, el {entregable.plazo:%d/%m/%Y}"
    else:
        cuando = f"vence en {dias} días, el {entregable.plazo:%d/%m/%Y}"
    return f"{entregable.referencia} {cuando}."


def generar_alertas_acta(hoy=None):
    """Aviso de acta pendiente (SDD del Sprint 2, RF-29 y §7.4). Idempotente. Devuelve la cantidad de avisos creados.

    Si el acta de una entrega sigue PENDIENTE más de ACTA_DIAS_PENDIENTE días desde la fecha de entrega, avisa al junior
    asignado y al senior revisor (tipo ACTA) UNA sola vez por entrega, aunque la tarea corra varias veces: la entrega se
    marca (`alerta_acta_en`) con un UPDATE condicional antes de crear los avisos, así dos ejecuciones simultáneas no
    duplican nada.
    """
    from django.db import transaction

    from apps.entregables.entregas import enlace_entregas, texto_acta_pendiente
    from apps.entregables.models import Entrega

    hoy = hoy or timezone.localdate()
    limite = hoy - datetime.timedelta(days=settings.ACTA_DIAS_PENDIENTE)
    pendientes = Entrega.objects.filter(
        acta_estado=Entrega.ActaEstado.PENDIENTE, alerta_acta_en__isnull=True, fecha_entrega__lt=limite,
    ).select_related("entregable__junior_asignado", "entregable__senior_revisor").order_by("pk")
    creadas = 0
    for entrega in pendientes:
        with transaction.atomic():
            reclamada = Entrega.objects.filter(pk=entrega.pk, alerta_acta_en__isnull=True).update(
                alerta_acta_en=timezone.now()
            )
            if not reclamada:
                continue
            e = entrega.entregable
            texto = texto_acta_pendiente(entrega, (hoy - entrega.fecha_entrega).days)[:255]
            for destinatario in dict.fromkeys([e.junior_asignado, e.senior_revisor]):
                Notificacion.objects.create(
                    usuario=destinatario, entregable=e, tipo=Notificacion.Tipo.ACTA, mensaje=texto,
                    enlace=enlace_entregas(e),
                )
                creadas += 1
    return creadas


def generar_alertas(hoy=None):
    """Crea una notificación por entregable, destinatario y umbral. Idempotente.

    Un entregable activo genera la alerta del umbral más urgente que ya alcanzó
    (p. ej. si faltan 4 días se emite la de 5 días). Vencidos no generan nuevas alertas.
    Con los umbrales 5,2,1,0 el aviso de 24 h (umbral 1) también sale una sola vez: lo garantiza la restricción
    «una alerta por umbral» de Notificacion. Devuelve la cantidad de notificaciones creadas.
    """
    hoy = hoy or timezone.localdate()
    umbrales = sorted(settings.ALERT_THRESHOLDS_DAYS)
    creadas = 0
    activos = Entregable.objects.exclude(estado=Entregable.Estado.HECHO).select_related(
        "junior_asignado", "senior_revisor"
    )
    for e in activos:
        dias = (e.plazo - hoy).days
        if dias < 0:
            continue
        # El umbral aplicable es el menor que sea >= días restantes.
        aplicables = [u for u in umbrales if u >= dias]
        if not aplicables:
            continue
        umbral = aplicables[0]
        texto = texto_vencimiento(e, dias)
        for destinatario in {e.junior_asignado, e.senior_revisor}:
            _, nueva = Notificacion.objects.get_or_create(
                usuario=destinatario, entregable=e, umbral=umbral, tipo=Notificacion.Tipo.VENCIMIENTO,
                defaults={"mensaje": texto},
            )
            creadas += nueva
    return creadas
