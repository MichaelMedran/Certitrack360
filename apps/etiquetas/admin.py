from django.contrib import admin

from .models import Etiqueta


@admin.register(Etiqueta)
class EtiquetaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "color", "linea_servicio", "activa")
    list_filter = ("activa", "color")
