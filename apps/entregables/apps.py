from django.apps import AppConfig


class EntregablesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.entregables'

    def ready(self):
        from . import signals  # noqa: F401  (registra la limpieza de archivos de adjuntos)
