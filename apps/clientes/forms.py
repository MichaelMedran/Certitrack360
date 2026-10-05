from django import forms

from apps.cuentas.models import Usuario

from .models import Cliente, Contrato, PlantillaTDR


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nombre", "sector", "activo"]


class ContratoForm(forms.ModelForm):
    class Meta:
        model = Contrato
        fields = ["cliente", "numero_contrato", "descripcion", "fecha_inicio", "fecha_fin", "senior_responsable", "juniors"]
        widgets = {
            "fecha_inicio": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "fecha_fin": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "juniors": forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["senior_responsable"].queryset = Usuario.objects.filter(rol=Usuario.Rol.SENIOR, is_active=True)
        self.fields["juniors"].queryset = Usuario.objects.filter(rol=Usuario.Rol.JUNIOR, is_active=True)
        self.fields["cliente"].queryset = Cliente.objects.filter(activo=True)

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
        help_text="Un campo por línea con el formato: Etiqueta | tipo. Tipos: texto, texto_largo, numero, fecha. "
        "Ejemplo: Número de informe | texto",
    )

    class Meta:
        model = PlantillaTDR
        fields = ["nombre", "cliente", "formato", "plazo_dias_por_defecto"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["campos_texto"].initial = "\n".join(
                f"{c['etiqueta']} | {c['tipo']}" for c in self.instance.campos_requeridos
            )

    def clean_campos_texto(self):
        campos, vistos = [], set()
        for n, linea in enumerate(self.cleaned_data["campos_texto"].splitlines(), start=1):
            if not linea.strip():
                continue
            etiqueta, _, tipo = (p.strip() for p in linea.partition("|"))
            tipo = tipo or "texto"
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
            campos.append({"nombre": nombre, "etiqueta": etiqueta, "tipo": tipo})
        if not campos:
            raise forms.ValidationError("Indique al menos un campo obligatorio.")
        return campos

    def save(self, commit=True):
        self.instance.campos_requeridos = self.cleaned_data["campos_texto"]
        return super().save(commit=commit)
