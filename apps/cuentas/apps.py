from django.apps import AppConfig


class CuentasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.cuentas'

    def ready(self):
        from . import signals  # noqa: F401  (registra los receptores del bloqueo de ingreso, RF-51)
