from django.apps import AppConfig


class CumplimientoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.cumplimiento"
    verbose_name = "Cumplimiento"

    def ready(self):
        from apps.entregables import extensiones

        from . import servicios

        # Penalidades incurridas y vigencia de los certificados del cliente: secciones del detalle y aviso con
        # confirmación al enviar a revisión si el cliente tiene un documento vencido.
        extensiones.registrar_seccion(servicios.seccion_penalidades)
        extensiones.registrar_seccion(servicios.seccion_vigencias)
        extensiones.registrar_condicion(servicios.condicion_vigencias)
