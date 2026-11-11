from django.apps import AppConfig


class EntregablesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.entregables'

    def ready(self):
        from . import extensiones, prioridad, signals  # noqa: F401  (signals: limpieza de archivos de adjuntos)

        extensiones.registrar_tarjeta(prioridad.enriquecer_tarjetas)  # insignia de prioridad (RF-42)
