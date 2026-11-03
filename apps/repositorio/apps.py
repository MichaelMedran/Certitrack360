from django.apps import AppConfig


class RepositorioConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.repositorio"
    verbose_name = "Repositorio"

    def ready(self):
        from . import signals  # noqa: F401
