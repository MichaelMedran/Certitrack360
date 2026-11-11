from django.contrib import admin

from .models import ConfiguracionReporte, ReporteAvance


@admin.register(ReporteAvance)
class ReporteAvanceAdmin(admin.ModelAdmin):
    list_display = ("datos_al", "origen", "generado_por", "generado_en")
    readonly_fields = ("origen", "generado_por", "generado_en", "datos_al", "datos", "archivo")

    def has_add_permission(self, request):
        return False


@admin.register(ConfiguracionReporte)
class ConfiguracionReporteAdmin(admin.ModelAdmin):
    list_display = ("periodicidad", "dia_semana", "dia_mes", "hora", "ultimo_automatico")
    readonly_fields = ("ultimo_automatico",)

    def has_add_permission(self, request):
        return not ConfiguracionReporte.objects.exists()
