from django.apps import AppConfig


class FacturacionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.facturacion"
    verbose_name = "Facturación"

    def ready(self):
        from apps.entregables import extensiones

        from . import verificacion

        # Verificación de factura (RF-46): condición para aprobar y sección «Factura» del detalle.
        extensiones.registrar_condicion(verificacion.condicion)
        extensiones.registrar_seccion(verificacion.seccion)
