from django.apps import AppConfig


class UrgenciasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.urgencias"
    verbose_name = "Urgencias"

    def ready(self):
        from apps.entregables import extensiones

        from . import secciones, servicios

        extensiones.registrar_tarjeta(servicios.enriquecer)
        extensiones.registrar_seccion(secciones.seccion_detalle)
        extensiones.registrar_al_mover(servicios.al_mover)
