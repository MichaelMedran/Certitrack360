from django import forms

from apps.cuentas.models import Usuario
from apps.entregables.tipos import TipoAdjunto

from .models import Cliente, Contrato, PlantillaTDR


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nombre", "sector", "activo"]


class ContratoForm(forms.ModelForm):
    class Meta:
        model = Contrato
        fields = [
            "cliente", "numero_contrato", "descripcion", "fecha_inicio", "fecha_fin", "senior_responsable", "juniors",
            "activo",
        ]
        widgets = {
            "fecha_inicio": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "fecha_fin": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "juniors": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["senior_responsable"].queryset = Usuario.objects.filter(rol=Usuario.Rol.SENIOR, is_active=True)
        self.fields["juniors"].queryset = Usuario.objects.filter(rol=Usuario.Rol.JUNIOR, is_active=True)
        # Un contrato existente conserva su cliente aunque este se haya dado de baja; los nuevos solo admiten clientes activos.
        permitidos = Cliente.objects.filter(activo=True)
        if self.instance.pk:
            permitidos = Cliente.objects.filter(activo=True) | Cliente.objects.filter(pk=self.instance.cliente_id)
        self.fields["cliente"].queryset = permitidos

    def clean(self):
        datos = super().clean()
        ini, fin = datos.get("fecha_inicio"), datos.get("fecha_fin")
        if ini and fin and fin < ini:
            self.add_error("fecha_fin", "La fecha de fin no puede ser anterior a la fecha de inicio.")
        return datos


class PlantillaForm(forms.ModelForm):
    campos_texto = forms.CharField(
        label="Campos obligatorios",
        widget=forms.Textarea(attrs={"rows": 6}),
        help_text="Un campo por línea con el formato: Etiqueta | tipo. Tipos: texto, texto_largo, numero, fecha, opcion. "
        "Ejemplos: «Número de informe | texto» · «Nivel | opcion | Alto, Medio, Bajo».",
    )

    adjuntos_requeridos = forms.MultipleChoiceField(
        label="Adjuntos obligatorios", choices=TipoAdjunto.choices, widget=forms.CheckboxSelectMultiple, required=False,
        help_text="Tipos de documento que el entregable debe tener antes de pasar a Verificación senior. Puede dejarlos vacíos.",
    )

    class Meta:
        model = PlantillaTDR
        fields = ["nombre", "cliente", "formato", "plazo_dias_por_defecto", "adjuntos_requeridos"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["campos_texto"].initial = "\n".join(self._linea(c) for c in self.instance.campos_requeridos)

    @staticmethod
    def _linea(campo):
        linea = f"{campo['etiqueta']} | {campo['tipo']}"
        if campo["tipo"] == "opcion":
            linea += " | " + ", ".join(campo.get("opciones", []))
        return linea

    def clean_campos_texto(self):
        campos, vistos = [], set()
        for n, linea in enumerate(self.cleaned_data["campos_texto"].splitlines(), start=1):
            if not linea.strip():
                continue
            partes = [p.strip() for p in linea.split("|", 2)]
            etiqueta, tipo = partes[0], (partes[1] if len(partes) > 1 and partes[1] else "texto")
            if not etiqueta:
                raise forms.ValidationError(f"Línea {n}: falta la etiqueta del campo.")
            if tipo not in PlantillaTDR.TIPOS_CAMPO:
                raise forms.ValidationError(
                    f"Línea {n}: el tipo «{tipo}» no es válido. Use: {', '.join(PlantillaTDR.TIPOS_CAMPO)}."
                )
            nombre = "c_" + "".join(ch if ch.isalnum() else "_" for ch in etiqueta.lower())
            if nombre in vistos:
                raise forms.ValidationError(f"Línea {n}: el campo «{etiqueta}» está repetido.")
            vistos.add(nombre)
            campo = {"nombre": nombre, "etiqueta": etiqueta, "tipo": tipo}
            if tipo == "opcion":
                opciones = list(dict.fromkeys(o.strip() for o in (partes[2] if len(partes) > 2 else "").split(",") if o.strip()))
                if len(opciones) < 2:
                    raise forms.ValidationError(
                        f"Línea {n}: el campo «{etiqueta}» es de tipo opcion y necesita al menos dos opciones "
                        "separadas por comas. Ejemplo: Nivel | opcion | Alto, Medio, Bajo."
                    )
                campo["opciones"] = opciones
            campos.append(campo)
        if not campos:
            raise forms.ValidationError("Indique al menos un campo obligatorio.")
        return campos

    def save(self, commit=True):
        self.instance.campos_requeridos = self.cleaned_data["campos_texto"]
        return super().save(commit=commit)
