from django import forms
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.cuentas.permisos import solo_gestion

from . import servicios
from .models import ConfiguracionReporte, ReporteAvance

MAX_LISTA = 60


class ConfiguracionForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionReporte
        fields = ["periodicidad", "dia_semana", "dia_mes", "hora"]
        widgets = {"hora": forms.TimeInput(format="%H:%M", attrs={"type": "time"})}

    def clean_dia_mes(self):
        dia = self.cleaned_data["dia_mes"]
        if not 1 <= dia <= 28:
            raise forms.ValidationError("Elija un día del 1 al 28.")
        return dia


@solo_gestion  # sin sesión: al ingreso; los demás roles: 403
def reportes(request):
    """Lista de reportes, botón «Generar reporte» y configuración de la periodicidad (RF-50)."""
    config = ConfiguracionReporte.cargar()
    if request.method == "POST":
        form = ConfiguracionForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Se guardó la periodicidad de los reportes automáticos.")
            return redirect("reportes")
    else:
        form = ConfiguracionForm(instance=config)
    return render(request, "reportes/lista.html", {
        "reportes": ReporteAvance.objects.select_related("generado_por")[:MAX_LISTA], "form": form, "config": config,
    })


@solo_gestion
@require_POST
def reporte_generar(request):
    reporte = servicios.generar(ReporteAvance.Origen.MANUAL, usuario=request.user)
    messages.success(request, "Se generó el reporte de avance.")
    return redirect("reporte_detalle", pk=reporte.pk)


@solo_gestion
def reporte_detalle(request, pk):
    reporte = get_object_or_404(ReporteAvance.objects.select_related("generado_por"), pk=pk)
    return render(request, "reportes/detalle.html", {"reporte": reporte, "datos": reporte.datos, "estados": reporte.datos["estados"]})


@solo_gestion
def reporte_pdf(request, pk):
    """Descarga el PDF guardado. No hay URL pública de medios: solo esta vista, con permiso."""
    reporte = get_object_or_404(ReporteAvance, pk=pk)
    try:
        archivo = reporte.archivo.open("rb")
    except (FileNotFoundError, ValueError):
        raise Http404("El archivo del reporte ya no está en el servidor.")
    nombre = f"reporte-avance-{timezone.localtime(reporte.datos_al):%Y%m%d-%H%M}.pdf"
    return FileResponse(archivo, as_attachment=True, filename=nombre, content_type="application/pdf")
