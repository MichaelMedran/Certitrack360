from django.contrib import admin

from .models import ConfiguracionReporte, ReporteAvance


@admin.register(ReporteAvance)
class ReporteAvanceAdmin(admin.ModelAdmin):
    list_display = ("datos_al", "origen", "generado_por", "generado_en")
    # El PDF no tiene URL pública (MEDIA_URL es None): el panel muestra su ubicación en texto, no un enlace.
    exclude = ("archivo",)
    readonly_fields = ("origen", "generado_por", "generado_en", "datos_al", "datos", "ruta_en_disco")

    @admin.display(description="Ubicación en el servidor")
    def ruta_en_disco(self, obj):
        return obj.archivo.name

    def has_add_permission(self, request):
        return False


@admin.register(ConfiguracionReporte)
class ConfiguracionReporteAdmin(admin.ModelAdmin):
    list_display = ("periodicidad", "dia_semana", "dia_mes", "hora", "ultimo_automatico")
    readonly_fields = ("ultimo_automatico",)

    def has_add_permission(self, request):
        return not ConfiguracionReporte.objects.exists()
