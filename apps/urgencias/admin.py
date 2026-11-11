from django.contrib import admin

from .models import AlertaUrgente, LecturaAlerta


class LecturaInline(admin.TabularInline):
    model = LecturaAlerta
    extra = 0
    readonly_fields = ("usuario", "leida_en")
    can_delete = False


@admin.register(AlertaUrgente)
class AlertaUrgenteAdmin(admin.ModelAdmin):
    list_display = ("entregable", "plazo_esperado", "fuera_de_horario", "activada_por", "activada_en", "aceptada_por", "cerrada_en")
    list_filter = ("fuera_de_horario",)
    inlines = [LecturaInline]
