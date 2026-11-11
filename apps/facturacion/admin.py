from django.contrib import admin

from .models import FacturaSimulada, VerificacionFactura


@admin.register(FacturaSimulada)
class FacturaSimuladaAdmin(admin.ModelAdmin):
    """La base simulada se administra aquí solo para la demostración; la plataforma nunca la modifica."""

    list_display = ("numero", "cliente_nombre", "contrato_numero", "estado", "fecha_emision", "monto")
    list_filter = ("estado",)
    search_fields = ("numero", "cliente_nombre", "contrato_numero")


@admin.register(VerificacionFactura)
class VerificacionFacturaAdmin(admin.ModelAdmin):
    list_display = ("numero", "resultado", "entregable", "usuario", "fecha")
    list_filter = ("resultado",)
    search_fields = ("numero",)
