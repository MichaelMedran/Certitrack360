"""Reportes de avance (SDD del Sprint 3, RF-50 y §7.11).

Las cifras salen de los registros, sin ingreso manual. El reporte automático lo dispara la tarea programada cada hora
(`generar_si_corresponde`) y es idempotente: a lo sumo uno por periodo, aunque la tarea corra varias veces o a la vez.
"""
import datetime
from collections import Counter

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.alertas.models import Notificacion
from apps.cuentas.models import Usuario
from apps.entregables.models import Entregable, Observacion

from . import pdf
from .models import ConfiguracionReporte, ReporteAvance

E = Entregable.Estado
P = ConfiguracionReporte.Periodicidad


def _fila(nombre, filas, pendientes, hoy, limite):
    """Cifras de un grupo de entregables (un contrato, un cliente o toda el área)."""
    por_estado = Counter(f["estado"] for f in filas)
    activos = [f for f in filas if f["estado"] != E.HECHO]
    return {
        "nombre": nombre,
        "total": len(filas),
        "activos": len(activos),
        "por_estado": {v: por_estado.get(v, 0) for v in E.values},
        "celdas": [por_estado.get(v, 0) for v in E.values],
        "vencidos": sum(1 for f in activos if f["plazo"] < hoy),
        "por_vencer": sum(1 for f in activos if hoy <= f["plazo"] <= limite),
        "observaciones_pendientes": pendientes,
    }


def calcular_datos(hoy=None, ahora=None):
    """Todas las cifras del reporte, por cliente y contrato y con los totales del área.

    Cuenta todos los entregables (el reporte es del área, para gerente y admin). «Vencidos» y «por vencer» (plazo dentro de
    `CONSOLIDADO_WINDOW_DAYS` días) no incluyen los entregados. «Observaciones pendientes» son las que aún no tienen acción
    correctiva (estado Pendiente). Devuelve un diccionario listo para guardarse como JSON.
    """
    ahora = ahora or timezone.now()
    hoy = hoy or timezone.localdate(ahora)
    ventana = settings.CONSOLIDADO_WINDOW_DAYS
    limite = hoy + datetime.timedelta(days=ventana)

    filas = list(Entregable.objects.values(
        "estado", "plazo", "contrato_id", "contrato__numero_contrato", "contrato__cliente_id", "contrato__cliente__nombre",
    ))
    obs_por_contrato = Counter(
        Observacion.objects.pendientes().values_list("entregable__contrato_id", flat=True)
    )

    por_cliente = {}
    for f in filas:
        cli = por_cliente.setdefault(f["contrato__cliente_id"], {"nombre": f["contrato__cliente__nombre"], "contratos": {}})
        cli["contratos"].setdefault(f["contrato_id"], {"nombre": f["contrato__numero_contrato"], "filas": []})["filas"].append(f)

    clientes = []
    for cli in sorted(por_cliente.values(), key=lambda c: c["nombre"].lower()):
        contratos = [
            _fila(c["nombre"], c["filas"], obs_por_contrato.get(cid, 0), hoy, limite)
            for cid, c in sorted(cli["contratos"].items(), key=lambda kv: kv[1]["nombre"])
        ]
        todas = [f for c in cli["contratos"].values() for f in c["filas"]]
        fila = _fila(cli["nombre"], todas, sum(c["observaciones_pendientes"] for c in contratos), hoy, limite)
        fila["contratos"] = contratos
        clientes.append(fila)

    return {
        "datos_al": ahora.isoformat(),
        "ventana_dias": ventana,
        "estados": [{"codigo": v, "etiqueta": str(etiqueta)} for v, etiqueta in E.choices],
        "totales": _fila("Área de Proyectos", filas, sum(obs_por_contrato.values()), hoy, limite),
        "clientes": clientes,
    }


def _avisar_a_gerentes(reporte):
    texto = f"Nuevo reporte de avance con datos al {timezone.localtime(reporte.datos_al):%d/%m/%Y %H:%M}."
    enlace = reverse("reporte_detalle", args=[reporte.pk])
    Notificacion.objects.bulk_create([
        Notificacion(usuario=g, tipo=Notificacion.Tipo.REPORTE, mensaje=texto, enlace=enlace)
        for g in Usuario.objects.filter(rol=Usuario.Rol.GERENTE, is_active=True)
    ])


def generar(origen, usuario=None, ahora=None):
    """Calcula los datos, guarda el reporte con su PDF y avisa a los gerentes activos (con enlace al reporte)."""
    ahora = ahora or timezone.now()
    datos = calcular_datos(ahora=ahora)
    etiqueta_origen = ReporteAvance.Origen(origen).label
    contenido = pdf.generar_pdf(datos, timezone.localtime(ahora), etiqueta_origen, usuario.nombre if usuario else "")
    reporte = ReporteAvance(origen=origen, generado_por=usuario, datos_al=ahora, datos=datos)
    try:
        with transaction.atomic():
            reporte.archivo.save("reporte.pdf", ContentFile(contenido), save=False)
            reporte.save()
            _avisar_a_gerentes(reporte)
    except Exception:
        if reporte.archivo.name:  # no dejar un PDF huérfano si se revierte el guardado
            reporte.archivo.storage.delete(reporte.archivo.name)
        raise
    return reporte


def momento_programado(config, ahora):
    """La hora de generación más reciente que ya pasó según la periodicidad (None si está desactivada)."""
    if config.periodicidad == P.DESACTIVADA:
        return None
    local = timezone.localtime(ahora)
    zona = local.tzinfo

    def en(dia):
        return datetime.datetime.combine(dia, config.hora, tzinfo=zona)

    hoy = local.date()
    if config.periodicidad == P.DIARIA:
        candidato = en(hoy)
        return candidato if candidato <= local else en(hoy - datetime.timedelta(days=1))
    if config.periodicidad == P.SEMANAL:
        dia = hoy - datetime.timedelta(days=(hoy.weekday() - config.dia_semana) % 7)
        candidato = en(dia)
        return candidato if candidato <= local else en(dia - datetime.timedelta(days=7))
    dia_mes = min(max(config.dia_mes, 1), 28)
    candidato = en(hoy.replace(day=dia_mes))
    if candidato <= local:
        return candidato
    anterior = hoy.replace(day=1) - datetime.timedelta(days=1)
    return en(anterior.replace(day=dia_mes))


def corresponde_generar(config, ahora):
    """True si ya llegó la hora del periodo actual y todavía no se generó el automático de ese periodo."""
    programado = momento_programado(config, ahora)
    if programado is None:
        return False
    return config.ultimo_automatico is None or config.ultimo_automatico < programado


def generar_si_corresponde(ahora=None):
    """Genera el reporte automático si toca. Devuelve el reporte o None. Idempotente y a prueba de ejecuciones simultáneas.

    Se «reclama» el periodo con un UPDATE condicional sobre `ultimo_automatico` antes de generar: de dos ejecuciones al
    mismo tiempo solo una lo logra. Si la generación falla, todo se revierte y se reintenta en la siguiente hora.
    """
    ahora = ahora or timezone.now()
    config = ConfiguracionReporte.cargar()
    if not corresponde_generar(config, ahora):
        return None
    programado = momento_programado(config, ahora)
    with transaction.atomic():
        reclamado = ConfiguracionReporte.objects.filter(pk=config.pk).filter(
            Q(ultimo_automatico__isnull=True) | Q(ultimo_automatico__lt=programado)
        ).update(ultimo_automatico=ahora)
        if not reclamado:
            return None
        return generar(ReporteAvance.Origen.AUTOMATICO, ahora=ahora)
