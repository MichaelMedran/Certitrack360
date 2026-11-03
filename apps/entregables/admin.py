from django.contrib import admin

from . import adjuntos
from .models import Adjunto, Entrega, Entregable, HistorialEstado, Observacion, RegistroTiempo, ResponsableApoyo

admin.site.register(Observacion)
admin.site.register(HistorialEstado)
admin.site.register(ResponsableApoyo)
admin.site.register(RegistroTiempo)


@admin.register(Entregable)
class EntregableAdmin(admin.ModelAdmin):
    """El código se asigna solo al crear (también desde aquí) y no se edita: se muestra de solo lectura."""

    list_display = ("codigo", "titulo", "contrato", "estado", "plazo")
    list_select_related = ("contrato__cliente",)
    list_filter = ("estado",)
    search_fields = ("codigo", "titulo", "id_tdr")
    readonly_fields = ("codigo",)


@admin.register(Adjunto)
class AdjuntoAdmin(admin.ModelAdmin):
    """Solo consulta y soporte. Los archivos no tienen URL pública, así que el panel no enlaza al archivo: muestra
    su ubicación en texto. Los adjuntos se suben desde el entregable (con sus permisos y su versionado)."""

    list_display = ("nombre_original", "tipo", "version", "bloqueado", "entregable", "subido_por", "subido_en")
    list_filter = ("tipo", "bloqueado")
    exclude = ("archivo",)
    readonly_fields = ("ruta_en_disco",)

    @admin.display(description="Ubicación en el servidor")
    def ruta_en_disco(self, obj):
        return obj.archivo.name

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        """Una versión bloqueada (enviada al cliente, cargo o acta) no se elimina ni desde el panel (RF-28)."""
        return not (obj is not None and adjuntos.esta_bloqueado(obj)) and super().has_delete_permission(request, obj)


@admin.register(Entrega)
class EntregaAdmin(admin.ModelAdmin):
    """Solo consulta y soporte: las entregas y las actas se registran desde el entregable (con sus permisos, el cargo
    obligatorio y el bloqueo de la versión enviada), nunca desde el panel."""

    list_display = ("entregable", "numero", "fecha_entrega", "medio", "acta_estado", "registrada_por")
    list_filter = ("acta_estado", "medio")
    search_fields = ("entregable__codigo", "entregable__titulo")
    list_select_related = ("entregable", "registrada_por")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
