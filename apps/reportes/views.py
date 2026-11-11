from apps.cuentas.permisos import solo_gestion
from django.shortcuts import render


@solo_gestion
def reportes(request):
    """Pantalla provisional: la construye el hito S3-H11."""
    return render(request, "en_construccion.html", {"titulo": "Reportes de avance", "hito": "S3-H11"})
