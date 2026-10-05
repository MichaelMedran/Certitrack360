from django.contrib import admin

from .models import Adjunto, Entregable, HistorialEstado, Observacion

admin.site.register(Entregable)
admin.site.register(Observacion)
admin.site.register(HistorialEstado)


@admin.register(Adjunto)
class AdjuntoAdmin(admin.ModelAdmin):
    # Los archivos no tienen URL pública: se muestran solo los metadatos y se suben desde el entregable.
    list_display = ("nombre_original", "tipo", "version", "entregable", "subido_por", "subido_en")
    list_filter = ("tipo",)
    readonly_fields = ("archivo",)
