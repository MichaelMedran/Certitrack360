"""Gestión de clientes, contratos y plantillas (solo Gerente y Admin)."""
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.cuentas.permisos import solo_gestion

from .forms import FILA_VACIA, TIPOS_CAMPO_ETIQUETAS, ClienteForm, ContratoForm, PlantillaForm
from .models import Cliente, Contrato, PlantillaTDR

ENTIDADES = {
    "clientes": {"modelo": Cliente, "form": ClienteForm, "titulo": "Clientes", "nuevo": "Nuevo cliente",
                 "guardado": "Se guardó el cliente."},
    "contratos": {"modelo": Contrato, "form": ContratoForm, "titulo": "Contratos", "nuevo": "Nuevo contrato",
                  "guardado": "Se guardó el contrato."},
    "plantillas": {"modelo": PlantillaTDR, "form": PlantillaForm, "titulo": "Plantillas", "nuevo": "Nueva plantilla",
                   "guardado": "Se guardó la plantilla."},
}


def _config(entidad):
    if entidad not in ENTIDADES:
        raise Http404
    return ENTIDADES[entidad]


@solo_gestion
def gestion(request):
    """Acceso común de «Gestión»: lleva a la primera pestaña."""
    return redirect("adm_lista", entidad="clientes")


@solo_gestion
def lista(request, entidad):
    config = _config(entidad)
    modelo = config["modelo"]
    qs = modelo.objects.all()
    if modelo is Contrato:
        qs = qs.select_related("cliente", "senior_responsable").prefetch_related("juniors")
    if modelo is PlantillaTDR:
        qs = qs.select_related("cliente")
    return render(request, "clientes/lista.html", {"entidad": entidad, "config": config, "objetos": qs})


@solo_gestion
def editar(request, entidad, pk=None):
    config = _config(entidad)
    objeto = get_object_or_404(config["modelo"], pk=pk) if pk else None
    form = config["form"](request.POST or None, instance=objeto)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, config["guardado"])
        return redirect("adm_lista", entidad=entidad)
    return render(request, "clientes/form.html", {
        "form": form, "entidad": entidad, "config": config, "objeto": objeto,
        "tipos_campo": TIPOS_CAMPO_ETIQUETAS, "fila_vacia": FILA_VACIA,
    })
