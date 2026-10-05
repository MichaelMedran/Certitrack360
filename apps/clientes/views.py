"""Administración de clientes, contratos y plantillas (solo Gerente y Admin)."""
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.cuentas.permisos import solo_gestion

from .forms import ClienteForm, ContratoForm, PlantillaForm
from .models import Cliente, Contrato, PlantillaTDR

# Configuración común de las tres entidades: (modelo, formulario, singular, plural, columnas)
ENTIDADES = {
    "clientes": (Cliente, ClienteForm, "cliente", "Clientes"),
    "contratos": (Contrato, ContratoForm, "contrato", "Contratos"),
    "plantillas": (PlantillaTDR, PlantillaForm, "plantilla", "Plantillas de TDR"),
}


def _config(entidad):
    if entidad not in ENTIDADES:
        raise Http404
    return ENTIDADES[entidad]


@solo_gestion
def administracion(request):
    return render(request, "clientes/administracion.html", {
        "n_clientes": Cliente.objects.count(),
        "n_contratos": Contrato.objects.count(),
        "n_plantillas": PlantillaTDR.objects.count(),
    })


@solo_gestion
def lista(request, entidad):
    modelo, _, singular, titulo = _config(entidad)
    qs = modelo.objects.all()
    if modelo is Contrato:
        qs = qs.select_related("cliente", "senior_responsable")
    if modelo is PlantillaTDR:
        qs = qs.select_related("cliente")
    return render(request, "clientes/lista.html", {
        "entidad": entidad, "titulo": titulo, "singular": singular, "objetos": qs,
    })


@solo_gestion
def editar(request, entidad, pk=None):
    modelo, form_cls, singular, titulo = _config(entidad)
    objeto = get_object_or_404(modelo, pk=pk) if pk else None
    form = form_cls(request.POST or None, instance=objeto)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Se guardó el {singular}.")
        return redirect("adm_lista", entidad=entidad)
    return render(request, "clientes/form.html", {
        "form": form, "entidad": entidad, "titulo": titulo, "singular": singular, "objeto": objeto,
    })
