"""Gestión de clientes, contratos, plantillas y líneas de servicio (solo Gerente y Admin)."""
from django.contrib import messages
from django.db.models import Count
from django.db.models.functions import Lower
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.cuentas.permisos import solo_gestion
from apps.entregables.filtros import entero

from .forms import FILA_VACIA, TIPOS_CAMPO_ETIQUETAS, ClienteForm, ContratoForm, LineaServicioForm, PlantillaForm
from .models import Cliente, Contrato, LineaServicio, PlantillaTDR

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
        qs = qs.select_related("cliente", "senior_responsable", "linea_servicio").prefetch_related("juniors")
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


def _linea_o_404(valor):
    """La línea de servicio con ese id, o 404 si el id no es un número válido (o está fuera de rango) o no existe."""
    pk = entero(valor)
    if pk is None:
        raise Http404("No existe esa línea de servicio.")
    return get_object_or_404(LineaServicio, pk=pk)


@solo_gestion  # sin sesión: al ingreso; junior y senior: 403, igual que el resto de Gestión
def lineas_servicio(request):
    """Pestaña «Líneas de servicio» (SDD del Sprint 2, RF-24; ruta /lineas-servicio/, GET y POST).

    GET: el catálogo y, con ?nueva o ?editar=<id>, el formulario de alta o de edición.
    POST: guarda una línea nueva o, si trae «linea», la edita (renombrar, activar o desactivar). No hay borrado: la baja
    es lógica y una línea en uso está protegida también en la base de datos.
    """
    editando, form = None, None
    if request.method == "POST":
        if "linea" in request.POST:  # edición: un id mal escrito o inexistente es 404 (nunca crea otra línea)
            editando = _linea_o_404(request.POST.get("linea"))
        form = LineaServicioForm(request.POST, instance=editando)
        if form.is_valid():
            linea = form.save()
            accion = "Se guardaron los cambios de" if editando else "Se creó"
            messages.success(request, f"{accion} la línea de servicio «{linea.nombre}».")
            return redirect("lineas_servicio")
    else:
        if "editar" in request.GET:
            editando = _linea_o_404(request.GET.get("editar"))
            form = LineaServicioForm(instance=editando)
        elif "nueva" in request.GET:
            form = LineaServicioForm()
    # Con GROUP BY Django no aplica el orden del modelo: se pide de nuevo, alfabético.
    lineas = LineaServicio.objects.annotate(n_contratos=Count("contratos")).order_by(Lower("nombre"))
    return render(request, "clientes/lineas.html", {
        "entidad": "lineas", "lineas": lineas, "form": form, "editando": editando,
    })
