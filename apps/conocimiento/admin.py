from django.contrib import admin

from .models import ConsultaAsistente, LeccionAprendida, Procedimiento

admin.site.register(LeccionAprendida)
admin.site.register(Procedimiento)
admin.site.register(ConsultaAsistente)
