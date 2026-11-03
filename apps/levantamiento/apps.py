from django.apps import AppConfig


class LevantamientoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.levantamiento"
    verbose_name = "Levantamiento"

    def ready(self):
        from . import signals  # noqa: F401  (registra la limpieza del archivo del TDR)
