from django.apps import AppConfig


class ExtraccionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.extraccion"
    verbose_name = "Extracción de datos"

    def ready(self):
        from apps.entregables import extensiones

        from . import secciones

        extensiones.registrar_seccion(secciones.seccion_detalle)
