"""Formularios de la alerta urgente: el de activar desde el detalle y los campos que suma «Nuevo entregable»."""
from django import forms

from . import servicios

ENTRADA_FECHA_HORA = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"]


def campo_naturaleza():
    return forms.CharField(
        label="Naturaleza de la urgencia", required=False, max_length=servicios.MAX_NATURALEZA,
        widget=forms.Textarea(attrs={"rows": 3}), help_text="Qué ocurre y qué se necesita.",
    )


def campo_plazo():
    return forms.DateTimeField(
        label="Plazo esperado", required=False, input_formats=ENTRADA_FECHA_HORA,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        help_text="Fecha y hora futuras (hora de Lima).",
        error_messages={"invalid": "El plazo esperado no tiene un formato válido de fecha y hora."},
    )


def validar_urgencia(datos, agregar_error):
    """Naturaleza y plazo esperado obligatorios (y el plazo futuro); `agregar_error(campo, mensaje)` recibe cada motivo."""
    try:
        servicios.validar_datos(datos.get("naturaleza"), datos.get("plazo_esperado"))
    except forms.ValidationError as exc:
        for mensaje in exc.messages:
            agregar_error("plazo_esperado" if "plazo" in mensaje.lower() else "naturaleza", mensaje)


class ActivarAlertaForm(forms.Form):
    naturaleza = campo_naturaleza()
    plazo_esperado = campo_plazo()

    def clean(self):
        datos = super().clean()
        if not self.errors:
            validar_urgencia(datos, self.add_error)
        return datos
