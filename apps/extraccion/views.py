"""Vistas de la extracción de datos (SDD del Sprint 3, §7.9 y §10): subir el documento y revisar la vista previa."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from apps.clientes.models import PlantillaTDR
from apps.entregables.filtros import entero
from apps.entregables.forms import contratos_para
from apps.entregables.models import Adjunto
from apps.entregables.visibilidad import entregables_visibles

from . import servicios


def _volver_a_crear(plantilla_id=None):
    url = reverse("entregable_nuevo")
    return redirect(f"{url}?plantilla={plantilla_id}#prellenar" if plantilla_id else url)


@login_required
@require_POST
def nueva(request):
    """Lee un documento subido (en «Nuevo entregable») o un adjunto ya subido (en el detalle) y abre la vista previa."""
    usuario = request.user
    entregable = None
    archivo = request.FILES.get("archivo")
    plantilla = None
    entregable_id = entero(request.POST.get("entregable"))
    if entregable_id is not None:
        entregable = get_object_or_404(
            entregables_visibles(usuario).select_related("contrato", "plantilla"), pk=entregable_id,  # 404 si no lo ve
        )
        if not servicios.puede_extraer(usuario, entregable):
            raise PermissionDenied
        adjunto = get_object_or_404(Adjunto.objects.filter(entregable=entregable), pk=entero(request.POST.get("adjunto")) or 0)
        try:
            with adjunto.archivo.open("rb") as origen:
                archivo = SimpleUploadedFile(adjunto.nombre_original, origen.read())
        except (FileNotFoundError, ValueError):
            raise Http404("El archivo no se encuentra en el servidor.")
        volver = redirect(reverse("entregable_detalle", args=[entregable.pk]) + "#extraer-datos")
    else:
        plantilla_id = entero(request.POST.get("plantilla"))
        plantilla = PlantillaTDR.objects.filter(pk=plantilla_id).first() if plantilla_id is not None else None
        if not usuario.puede_crear_entregables:
            raise PermissionDenied  # «Nuevo entregable» es de seniors, gerente y admin
        volver = _volver_a_crear(plantilla.pk if plantilla else None)
    try:
        if archivo is None:
            raise ValidationError("Elija el documento (PDF o imagen) del que quiere extraer los datos.")
        extraccion = servicios.extraer(usuario, archivo, plantilla=plantilla, entregable=entregable)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return volver
    return redirect("extraccion_vista", pk=extraccion.pk)


def _filas(extraccion, valores=None, errores=None):
    """Las filas de la tabla de la vista previa: el campo con el valor a mostrar (el propuesto o lo que la persona editó)."""
    filas = []
    for i, campo in enumerate(extraccion.campos):
        valor = valores[i] if valores is not None and i < len(valores) else campo.get("confirmado", campo["valor"])
        filas.append({"i": i, "campo": campo, "valor": valor, "error": (errores or {}).get(i),
                      "dudoso": campo["estado"] != "ok"})
    return filas


@login_required
@require_http_methods(["GET", "POST"])
def vista(request, pk):
    """Vista previa editable. «Aplicar» confirma (y solo entonces algo pasa); «Descartar» borra la propuesta."""
    usuario = request.user
    extraccion = get_object_or_404(servicios.propias(usuario), pk=pk)  # solo las propias; si no, 404
    valores, errores = None, None
    if request.method == "POST" and not extraccion.aplicada_en:
        if request.POST.get("accion") == "descartar":
            volver = (reverse("entregable_detalle", args=[extraccion.entregable_id]) if extraccion.entregable_id
                      else reverse("entregable_nuevo") + (f"?plantilla={extraccion.plantilla_id}" if extraccion.plantilla_id else ""))
            servicios.descartar(extraccion)
            messages.info(request, "Se descartó la extracción: no se guardó ningún dato.")
            return redirect(volver)
        valores = [request.POST.get(f"valor-{i}", "") for i in range(len(extraccion.campos))]
        try:
            aplicados = servicios.confirmar(extraccion, usuario, valores)
        except ValidationError as error:
            if hasattr(error, "error_dict"):
                errores = {int(i): e[0].messages[0] for i, e in error.error_dict.items()}
            else:
                messages.error(request, error.messages[0])
        else:
            if extraccion.entregable_id:
                messages.success(request, "Se completaron los datos de la plantilla: " + (", ".join(aplicados) or "ninguno (todos estaban vacíos)") + ".")
                return redirect(reverse("entregable_detalle", args=[extraccion.entregable_id]) + "#extraer-datos")
            messages.success(request, "Valores aplicados al formulario. Revíselos: se validan igual que una carga manual.")
            return redirect(f"{reverse('entregable_nuevo')}?plantilla={extraccion.plantilla_id or ''}&extraccion={extraccion.pk}")
    return render(request, "extraccion/vista.html", {
        "extraccion": extraccion, "filas": _filas(extraccion, valores, errores), "motores": servicios.estado_de_motores(),
        "contratos": contratos_para(usuario) if not extraccion.entregable_id else [],
        "aplicada": bool(extraccion.aplicada_en),
    })
