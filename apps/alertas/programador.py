"""Tareas programadas (SDD §8.3: APScheduler): alertas de vencimiento e indexación de lecciones del asistente."""
import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)

ALERTAS_CADA_MINUTOS = 60
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
    from apps.alertas.servicios import generar_alertas

    creadas = generar_alertas()
    logger.info("Alertas de vencimiento generadas: %s", creadas)
    return creadas


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
    return programador
