from django.contrib import admin

from .models import FichaLevantamiento, ItemFicha


@admin.register(FichaLevantamiento)
class FichaLevantamientoAdmin(admin.ModelAdmin):
    """Solo consulta y soporte. El archivo del TDR no tiene URL pública, así que el panel muestra su ruta en texto."""

    list_display = ("contrato", "id_tdr", "estado", "estado_documental", "responsable", "actualizada_en")
    list_filter = ("estado", "estado_documental")
    search_fields = ("id_tdr", "contrato__numero_contrato", "contrato__cliente__nombre")
    list_select_related = ("contrato__cliente", "responsable")
    exclude = ("archivo_tdr",)
    readonly_fields = ("ruta_en_disco", "estado_inicial", "confirmada_por", "confirmada_en")

    @admin.display(description="Ubicación del archivo en el servidor")
    def ruta_en_disco(self, obj):
        return obj.archivo_tdr.name if obj.archivo_tdr else "—"


@admin.register(ItemFicha)
class ItemFichaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "ficha", "plantilla", "frecuencia", "primera_fecha", "hasta", "junior", "senior")
    list_filter = ("frecuencia",)
    list_select_related = ("ficha__contrato", "plantilla", "junior", "senior")
