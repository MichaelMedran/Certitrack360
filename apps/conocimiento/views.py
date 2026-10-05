from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from . import servicios


@login_required
def asistente(request):
    pregunta = request.GET.get("q", "").strip()
    contexto = {"pregunta": pregunta}
    if pregunta:
        contexto.update(servicios.responder(pregunta, request.user))
        contexto["buscado"] = True
    return render(request, "conocimiento/asistente.html", contexto)
