from django.contrib import admin

from .models import DocumentoRepositorio, RegistroAccesoDocumento, VersionDocumento


@admin.register(DocumentoRepositorio)
class DocumentoRepositorioAdmin(admin.ModelAdmin):
    list_display = ("titulo", "categoria", "cliente", "tipo_documento", "linea_servicio", "activo", "creado_en")
    list_filter = ("categoria", "tipo_documento", "activo")
    search_fields = ("titulo",)


@admin.register(VersionDocumento)
class VersionDocumentoAdmin(admin.ModelAdmin):
    list_display = ("documento", "numero", "nombre_original", "vigente", "subido_por", "subido_en")
    list_filter = ("vigente",)


@admin.register(RegistroAccesoDocumento)
class RegistroAccesoDocumentoAdmin(admin.ModelAdmin):
    list_display = ("version", "usuario", "accion", "fecha")
    list_filter = ("accion",)
