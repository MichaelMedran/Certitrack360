from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),  # panel técnico (solo rol ADMIN)
    path("", include("apps.cuentas.urls")),
    path("", include("apps.clientes.urls")),
    path("", include("apps.entregables.urls")),
    path("", include("apps.calendario.urls")),
    path("", include("apps.alertas.urls")),
    path("", include("apps.consolidado.urls")),
    path("", include("apps.conocimiento.urls")),
]
