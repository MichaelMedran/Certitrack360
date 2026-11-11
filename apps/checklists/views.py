from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def checklists(request):
    """Pantalla provisional: la construye el hito S3-H5."""
    return render(request, "en_construccion.html", {"titulo": "Checklists", "hito": "S3-H5"})


@login_required
def calidad(request):
    """Pantalla provisional: la construye el hito S3-H6."""
    return render(request, "en_construccion.html", {"titulo": "Checklist de calidad", "hito": "S3-H6"})
