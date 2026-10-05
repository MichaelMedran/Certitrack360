from django.contrib import admin

from .models import Adjunto, Entregable, HistorialEstado, Observacion

admin.site.register(Entregable)
admin.site.register(Observacion)
admin.site.register(HistorialEstado)


@admin.register(Adjunto)
class AdjuntoAdmin(admin.ModelAdmin):
    """Solo consulta y soporte. Los archivos no tienen URL pública, así que el panel no enlaza al archivo: muestra
    su ubicación en texto. Los adjuntos se suben desde el entregable (con sus permisos y su versionado)."""

    list_display = ("nombre_original", "tipo", "version", "entregable", "subido_por", "subido_en")
    list_filter = ("tipo",)
    exclude = ("archivo",)
    readonly_fields = ("ruta_en_disco",)

    @admin.display(description="Ubicación en el servidor")
    def ruta_en_disco(self, obj):
        return obj.archivo.name

    def has_add_permission(self, request):
        return False
