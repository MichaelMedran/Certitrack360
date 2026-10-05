from django.contrib import admin

from .models import Entregable, HistorialEstado, Observacion

admin.site.register(Entregable)
admin.site.register(Observacion)
admin.site.register(HistorialEstado)
