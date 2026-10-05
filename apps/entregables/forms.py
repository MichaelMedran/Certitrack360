import datetime

from django import forms
from django.utils import timezone

from apps.clientes.models import Contrato
from apps.cuentas.models import Usuario

from .models import Entregable, TipoError
from .tipos import TipoAdjunto


def contratos_para(usuario):
    qs = Contrato.objects.select_related("cliente")
    if usuario.es_gerente_o_admin:
        return qs
    return qs.filter(senior_responsable=usuario)


class EntregableForm(forms.Form):
    """Formulario con Poka-Yoke: los campos obligatorios salen de la plantilla TDR."""

    contrato = forms.ModelChoiceField(
        queryset=Contrato.objects.none(), label="Contrato",
        error_messages={"required": "Falta elegir el contrato."},
    )
    titulo = forms.CharField(label="Título", max_length=200, error_messages={"required": "Falta el título."})
    plazo = forms.DateField(
        label="Plazo de entrega", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        error_messages={"required": "Falta el plazo de entrega.", "invalid": "El plazo no es una fecha válida."},
    )
    junior_asignado = forms.ModelChoiceField(
        queryset=Usuario.objects.none(), label="Junior asignado",
        error_messages={"required": "Falta asignar un junior."},
    )

    def __init__(self, usuario, plantilla, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plantilla = plantilla
        self.fields["contrato"].queryset = contratos_para(usuario)
        self.fields["junior_asignado"].queryset = Usuario.objects.filter(rol=Usuario.Rol.JUNIOR, is_active=True)
        if not self.is_bound and plantilla:
            self.fields["plazo"].initial = timezone.localdate() + datetime.timedelta(days=plantilla.plazo_dias_por_defecto)
        self.campos_dinamicos = []
        for c in (plantilla.campos_requeridos if plantilla else []):
            msg = {"required": f"Falta completar el campo «{c['etiqueta']}»."}
            tipo = c.get("tipo", "texto")
            if tipo == "numero":
                campo = forms.DecimalField(label=c["etiqueta"], error_messages={**msg, "invalid": f"«{c['etiqueta']}» debe ser un número."})
            elif tipo == "fecha":
                campo = forms.DateField(
                    label=c["etiqueta"], widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                    error_messages={**msg, "invalid": f"«{c['etiqueta']}» debe ser una fecha válida."},
                )
            elif tipo == "texto_largo":
                campo = forms.CharField(label=c["etiqueta"], widget=forms.Textarea(attrs={"rows": 3}), error_messages=msg)
            else:
                campo = forms.CharField(label=c["etiqueta"], max_length=255, error_messages=msg)
            self.fields[c["nombre"]] = campo
            self.campos_dinamicos.append(c["nombre"])

    def clean_plazo(self):
        plazo = self.cleaned_data["plazo"]
        if plazo < timezone.localdate():
            raise forms.ValidationError("El plazo no puede ser anterior a hoy.")
        return plazo

    def clean(self):
        datos = super().clean()
        contrato, junior = datos.get("contrato"), datos.get("junior_asignado")
        if contrato and junior and not contrato.juniors.filter(pk=junior.pk).exists():
            self.add_error("junior_asignado", "Ese junior no está asignado al contrato elegido.")
        return datos

    def guardar(self, usuario):
        d = self.cleaned_data
        valores = {}
        for nombre in self.campos_dinamicos:
            v = d[nombre]
            valores[nombre] = v.isoformat() if isinstance(v, datetime.date) else (str(v) if not isinstance(v, str) else v)
        return Entregable.objects.create(
            contrato=d["contrato"], plantilla=self.plantilla, titulo=d["titulo"], datos=valores, plazo=d["plazo"],
            junior_asignado=d["junior_asignado"], senior_revisor=d["contrato"].senior_responsable, creado_por=usuario,
        )


class AdjuntoForm(forms.Form):
    """Campos de la subida. La validación de extensión y tamaño la hace `adjuntos.validar_archivo`."""

    tipo = forms.ChoiceField(
        choices=TipoAdjunto.choices, label="Tipo",
        error_messages={"required": "Elija el tipo de adjunto.", "invalid_choice": "Elija un tipo de adjunto válido."},
    )
    archivo = forms.FileField(
        label="Archivo",
        error_messages={
            "required": "Elija el archivo que desea subir.",
            "missing": "Elija el archivo que desea subir.",
            "empty": "El archivo está vacío.",
            "invalid": "No se pudo leer el archivo.",
        },
    )
    comentario = forms.CharField(
        label="Comentario (opcional)", max_length=255, required=False,
        error_messages={"max_length": "El comentario no puede superar los 255 caracteres."},
    )


class ObservacionForm(forms.Form):
    tipo_error = forms.ChoiceField(choices=TipoError.choices, label="Tipo de error")
    descripcion = forms.CharField(label="Descripción", widget=forms.Textarea(attrs={"rows": 3}))
