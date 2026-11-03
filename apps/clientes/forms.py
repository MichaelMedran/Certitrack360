import re

from django import forms
from django.db.models import Q

from apps.cuentas.models import Usuario
from apps.entregables.models import Entregable
from apps.entregables.tipos import TipoAdjunto

from .models import Cliente, Contrato, LineaServicio, PlantillaTDR

TIPOS_CAMPO_ETIQUETAS = [
    ("texto", "Texto"), ("texto_largo", "Texto largo"), ("numero", "Número"), ("fecha", "Fecha"), ("opcion", "Opción"),
]
FILA_VACIA = {"nombre": "", "etiqueta": "", "tipo": "texto", "opciones": "", "error": ""}
CLAVE_VALIDA = re.compile(r"c_\w{1,80}")


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nombre", "sector", "activo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sector"].choices = [("", "— Elija el sector —")] + list(Cliente.Sector.choices)


class LineaServicioForm(forms.ModelForm):
    """Alta y edición de una línea de servicio: nombre (único, sin distinguir mayúsculas) y si está activa."""

    class Meta:
        model = LineaServicio
        fields = ["nombre", "activa"]
        labels = {"nombre": "Nombre", "activa": "Activa"}
        error_messages = {
            "nombre": {
                "required": "Falta el nombre de la línea de servicio.",
                "max_length": "El nombre no puede superar los 80 caracteres.",
            },
        }

    def clean_nombre(self):
        nombre = " ".join(self.cleaned_data["nombre"].split())
        # El catálogo es pequeño: se compara en Python para no depender de cómo cada base de datos trata las tildes.
        otras = LineaServicio.objects.exclude(pk=self.instance.pk).values_list("nombre", flat=True)
        if any(otra.casefold() == nombre.casefold() for otra in otras):
            raise forms.ValidationError("Ya existe una línea de servicio con ese nombre.")
        return nombre


class ContratoForm(forms.ModelForm):
    """Contrato. La línea de servicio (SDD del Sprint 2, RF-24) es obligatoria aquí aunque en la base de datos sea
    opcional (los contratos anteriores no la tienen). Compatibilidad (RNF-11): una petición que no trae el campo
    —un formulario anterior al Sprint 2— no lo toca; la pantalla siempre lo envía."""

    class Meta:
        model = Contrato
        fields = [
            "cliente", "numero_contrato", "descripcion", "linea_servicio", "fecha_inicio", "fecha_fin",
            "senior_responsable", "juniors", "activo",
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
        self.fields["cliente"].empty_label = "— Elija el cliente —"
        self.fields["senior_responsable"].empty_label = "— Elija el senior —"
        self._preparar_linea()

    def _preparar_linea(self):
        if self.is_bound and "linea_servicio" not in self.data:
            del self.fields["linea_servicio"]  # petición anterior al Sprint 2: el contrato conserva la línea que tenga
            return
        campo = self.fields["linea_servicio"]
        # Igual que con el cliente: las líneas inactivas no se ofrecen, salvo la que el contrato ya tiene.
        condicion = Q(activa=True)
        if self.instance.linea_servicio_id:
            condicion |= Q(pk=self.instance.linea_servicio_id)
        campo.queryset = LineaServicio.objects.filter(condicion)
        campo.required = True
        campo.empty_label = "— Elija la línea de servicio —"
        campo.error_messages = {
            **campo.error_messages,
            "required": "Falta elegir la línea de servicio.",
            "invalid_choice": "Elija una línea de servicio activa de la lista.",
        }

    def clean(self):
        datos = super().clean()
        ini, fin = datos.get("fecha_inicio"), datos.get("fecha_fin")
        if ini and fin and fin < ini:
            self.add_error("fecha_fin", "La fecha de fin no puede ser anterior a la fecha de inicio.")
        return datos


def _en(lista, i):
    return lista[i] if i < len(lista) else ""


class PlantillaForm(forms.ModelForm):
    """Plantilla de TDR. Los campos obligatorios se editan como una lista de filas (etiqueta, tipo, opciones) que llega
    en los parámetros repetidos campo_nombre / campo_etiqueta / campo_tipo / campo_opciones."""

    adjuntos_requeridos = forms.MultipleChoiceField(
        label="Adjuntos obligatorios", choices=TipoAdjunto.choices, widget=forms.CheckboxSelectMultiple, required=False,
        help_text=(
            f"Tipos de documento que el entregable debe tener antes de pasar a {Entregable.Estado.VERIFICACION_SENIOR.label}. "
            "Puede dejarlos vacíos."
        ),
    )

    class Meta:
        model = PlantillaTDR
        fields = ["nombre", "cliente", "formato", "plazo_dias_por_defecto", "adjuntos_requeridos"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cliente"].empty_label = "Genérica (para todos los clientes)"
        self.campos_limpios = []
        self.filas = self._filas()

    def _filas(self):
        """Las filas que muestra el editor: lo enviado si el formulario viene de un POST, o lo guardado."""
        if self.is_bound:
            nombres, etiquetas = self.data.getlist("campo_nombre"), self.data.getlist("campo_etiqueta")
            tipos, opciones = self.data.getlist("campo_tipo"), self.data.getlist("campo_opciones")
            return [
                {"nombre": _en(nombres, i), "etiqueta": etiqueta, "tipo": _en(tipos, i) or "texto",
                 "opciones": _en(opciones, i), "error": ""}
                for i, etiqueta in enumerate(etiquetas)
            ]
        if self.instance.pk:
            return [
                {"nombre": c["nombre"], "etiqueta": c["etiqueta"], "tipo": c["tipo"],
                 "opciones": ", ".join(c.get("opciones", [])), "error": ""}
                for c in self.instance.campos_requeridos
            ]
        return [dict(FILA_VACIA)]

    @staticmethod
    def _clave(previa, etiqueta):
        """La clave interna de un campo identifica sus valores en los entregables ya creados: se conserva al renombrarlo."""
        if CLAVE_VALIDA.fullmatch(previa or ""):
            return previa
        return "c_" + "".join(ch if ch.isalnum() else "_" for ch in etiqueta.lower())

    def clean(self):
        datos = super().clean()
        campos, claves, errores = [], set(), []

        def rechazar(fila, mensaje):
            fila["error"] = mensaje
            errores.append(mensaje)

        for fila in self.filas:
            etiqueta = fila["etiqueta"].strip()
            if not etiqueta:
                continue  # una fila en blanco se ignora
            tipo = fila["tipo"]
            if tipo not in PlantillaTDR.TIPOS_CAMPO:
                rechazar(fila, f"El tipo del campo «{etiqueta}» no es válido.")
                continue
            clave = self._clave(fila["nombre"], etiqueta)
            if clave in claves:
                rechazar(fila, f"El campo «{etiqueta}» está repetido.")
                continue
            campo = {"nombre": clave, "etiqueta": etiqueta, "tipo": tipo}
            if tipo == "opcion":
                opciones = list(dict.fromkeys(o.strip() for o in fila["opciones"].split(",") if o.strip()))
                if len(opciones) < 2:
                    rechazar(fila, f"El campo «{etiqueta}» es de tipo opción y necesita al menos dos opciones separadas por comas.")
                    continue
                campo["opciones"] = opciones
            claves.add(clave)
            campos.append(campo)
        if not campos and not errores:
            errores.append("Agregue al menos un campo obligatorio.")
        for mensaje in errores:
            self.add_error(None, mensaje)
        self.campos_limpios = campos
        return datos

    def save(self, commit=True):
        self.instance.campos_requeridos = self.campos_limpios
        return super().save(commit=commit)
