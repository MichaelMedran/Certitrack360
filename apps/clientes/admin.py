from django.contrib import admin

from .models import Cliente, Contrato, LineaServicio, PlantillaTDR

admin.site.register(Cliente)
admin.site.register(Contrato)
admin.site.register(PlantillaTDR)


@admin.register(LineaServicio)
class LineaServicioAdmin(admin.ModelAdmin):
    """Se administra en Gestión › Líneas de servicio. Una línea en uso no se puede borrar (PROTECT): se desactiva."""

    list_display = ("nombre", "activa")
    list_filter = ("activa",)
