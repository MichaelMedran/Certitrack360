from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Ausencia, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Rol en CertiTrack", {"fields": ("rol", "puesto")}),)
    add_fieldsets = UserAdmin.add_fieldsets + ((None, {"fields": ("rol", "puesto")}),)
    list_display = ("username", "first_name", "last_name", "rol", "puesto", "is_active")
    list_filter = ("rol", "is_active")
    # Se derivan del rol: solo ADMIN entra al panel técnico.
    readonly_fields = ("is_staff", "is_superuser")


@admin.register(Ausencia)
class AusenciaAdmin(admin.ModelAdmin):
    list_display = ("usuario", "desde", "hasta", "motivo", "registrada_por")
    list_select_related = ("usuario", "registrada_por")
    list_filter = ("desde",)
    search_fields = ("usuario__username", "usuario__first_name", "usuario__last_name", "motivo")
