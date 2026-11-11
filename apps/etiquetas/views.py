from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def etiquetas(request):
    """Pantalla provisional: la construye el hito S3-H2."""
    return render(request, "en_construccion.html", {"titulo": "Etiquetas", "hito": "S3-H2"})
