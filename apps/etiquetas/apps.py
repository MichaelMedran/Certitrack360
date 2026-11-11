from django.apps import AppConfig


class EtiquetasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.etiquetas"
    verbose_name = "Etiquetas"

    def ready(self):
        from apps.entregables import extensiones

        from . import secciones, servicios, signals  # noqa: F401  (registra la etiqueta de cada línea nueva)

        extensiones.registrar_tarjeta(servicios.enriquecer)
        extensiones.registrar_seccion(secciones.seccion_detalle)
