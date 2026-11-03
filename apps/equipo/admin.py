from django.contrib import admin

from .models import ActividadPlan, AvanceActividad, Incorporacion, PlanIncorporacion

admin.site.register(PlanIncorporacion)
admin.site.register(ActividadPlan)
admin.site.register(Incorporacion)
admin.site.register(AvanceActividad)
