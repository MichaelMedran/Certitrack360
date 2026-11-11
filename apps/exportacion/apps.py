from django.apps import AppConfig


class ExportacionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.exportacion"
    verbose_name = "Exportación"

    def ready(self):
        from apps.entregables import extensiones

        from . import servicios

        def seccion(usuario, entregable):
            """Sección «Exportar» del detalle (RF-47): botones, lo que falta y las exportaciones anteriores."""
            if not servicios.puede_exportar(usuario, entregable):
                return None
            return {
                "orden": 60,
                "plantilla": "exportacion/_seccion.html",
                "contexto": {
                    "faltantes": servicios.faltantes(entregable),
                    "exportaciones": servicios.exportaciones(entregable),
                },
            }

        extensiones.registrar_seccion(seccion)
