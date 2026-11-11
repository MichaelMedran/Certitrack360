from django import forms

from . import servicios
from .models import Etiqueta


class EtiquetaForm(forms.ModelForm):
    """Alta y edición de una etiqueta: nombre (único sin distinguir mayúsculas) y color de una lista cerrada."""

    class Meta:
        model = Etiqueta
        fields = ["nombre", "color"]
        labels = {"nombre": "Nombre", "color": "Color"}
        error_messages = {
            "nombre": {"required": "Falta el nombre de la etiqueta.", "max_length": "El nombre no puede superar los 40 caracteres."},
            "color": {"required": "Elija un color.", "invalid_choice": "Elija uno de los colores de la lista."},
        }

    def clean_nombre(self):
        nombre = servicios.nombre_normalizado(self.cleaned_data["nombre"])
        if not nombre:
            raise forms.ValidationError("Falta el nombre de la etiqueta.")
        if servicios.nombre_en_uso(nombre, self.instance.pk):
            raise forms.ValidationError("Ya existe una etiqueta con ese nombre.")
        return nombre

    def validate_constraints(self):
        pass  # la unicidad sin distinguir mayúsculas la revisa clean_nombre (y la restricción de la base de datos)
