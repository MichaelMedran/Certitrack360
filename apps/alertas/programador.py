"""Tareas programadas (SDD §8.3: APScheduler): alertas de vencimiento e indexación de lecciones del asistente."""
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)

ALERTAS_CADA_MINUTOS = 60
WHATSAPP_CADA_MINUTOS = 1
INDEXACION_HORA = 2  # 02:00, hora de Lima


def _con_conexion_limpia(tarea):
    """Un proceso que vive días no puede arrastrar conexiones de base de datos vencidas."""

    def envoltura():
        close_old_connections()
        try:
            return tarea()
        finally:
            close_old_connections()

    envoltura.__name__ = tarea.__name__
    return envoltura


def tarea_alertas():
    from apps.alertas.servicios import generar_alertas, generar_alertas_acta

    creadas = generar_alertas()
    logger.info("Alertas de vencimiento generadas: %s", creadas)
    actas = generar_alertas_acta()  # acta de conformidad pendiente: una sola vez por entrega (RF-29)
    logger.info("Alertas de acta pendiente generadas: %s", actas)
    tarea_vigencias()
    tarea_reporte()
    return creadas + actas


def tarea_vigencias():
    """Certificados y documentos del cliente por vencer o vencidos. Un fallo no debe frenar las demás alertas."""
    from apps.cumplimiento.servicios import generar_alertas_vigencia

    try:
        creadas = generar_alertas_vigencia()
    except Exception:  # noqa: BLE001  (se registra y se reintenta en la siguiente hora)
        logger.exception("No se pudieron generar los avisos de vigencia")
        return 0
    logger.info("Avisos de vigencia de documentos generados: %s", creadas)
    return creadas


def tarea_reporte():
    """Reporte de avance automático (RF-50): a lo sumo uno por periodo. Un fallo no debe frenar las alertas."""
    from apps.reportes.servicios import generar_si_corresponde

    try:
        reporte = generar_si_corresponde()
    except Exception:  # noqa: BLE001  (se registra y se reintenta en la siguiente hora)
        logger.exception("No se pudo generar el reporte de avance automático")
        return None
    if reporte:
        logger.info("Reporte de avance automático generado: %s", reporte.pk)
    return reporte


def tarea_whatsapp():
    """Envía por WhatsApp los avisos pendientes (solo si el canal está configurado)."""
    from apps.alertas import whatsapp

    enviados, fallidos = whatsapp.despachar()
    if enviados or fallidos:
        logger.info("WhatsApp: %s enviados, %s con error", enviados, fallidos)
    return enviados, fallidos


def tarea_lecciones():
    from apps.conocimiento.servicios import indexar_lecciones

    nuevas, indexadas, aviso = indexar_lecciones()
    logger.info("Lecciones nuevas: %s · embeddings: %s", nuevas, indexadas)
    if aviso:
        logger.warning(aviso)
    return nuevas, indexadas


def crear_programador():
    """Arma el planificador con sus tareas (sin iniciarlo, para poder probarlo)."""
    programador = BlockingScheduler(timezone=settings.TIME_ZONE)
    programador.add_job(
        _con_conexion_limpia(tarea_alertas), "interval", minutes=ALERTAS_CADA_MINUTOS, id="alertas",
        name="Alertas de vencimiento", max_instances=1, coalesce=True,
    )
    programador.add_job(
        _con_conexion_limpia(tarea_lecciones), "cron", hour=INDEXACION_HORA, minute=0, id="lecciones",
        name="Indexación de lecciones aprendidas", max_instances=1, coalesce=True,
    )
    if settings.WHATSAPP_CONECTOR:
        programador.add_job(
            _con_conexion_limpia(tarea_whatsapp), "interval", minutes=WHATSAPP_CADA_MINUTOS, id="whatsapp",
            name="Avisos por WhatsApp", max_instances=1, coalesce=True,
        )
    return programador
