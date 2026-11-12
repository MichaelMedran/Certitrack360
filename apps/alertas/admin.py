from django.contrib import admin

from .models import EnvioWhatsApp


@admin.register(EnvioWhatsApp)
class EnvioWhatsAppAdmin(admin.ModelAdmin):
    """Rastro de los avisos enviados por WhatsApp: solo lectura."""

    list_display = ("creado_en", "numero", "estado", "intentos", "error", "enviado_en")
    list_filter = ("estado",)
    search_fields = ("numero", "notificacion__mensaje")
    list_select_related = ("notificacion",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
