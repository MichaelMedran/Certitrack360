import datetime

from django import forms
from django.utils import timezone

from apps.clientes.models import Contrato
from apps.cuentas.models import Usuario

from . import adjuntos
from .models import Entregable, TipoError
from .tipos import TipoAdjunto


def contratos_para(usuario):
    """Contratos en los que el usuario puede crear entregables: vigentes (baja lógica) y, si es senior, a su cargo."""
    qs = Contrato.objects.select_related("cliente", "linea_servicio").filter(activo=True, cliente__activo=True)
    if usuario.es_gerente_o_admin:
        return qs
    return qs.filter(senior_responsable=usuario)


class SelectorDeContrato(forms.Select):
    """Cada opción lleva el cliente y la línea de servicio del contrato: el formulario los muestra en solo lectura
    y `certitrack.js` los actualiza al cambiar de contrato (atributo data-reflejar)."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        opcion = super().create_option(name, value, label, selected, index, subindex, attrs)
        contrato = getattr(value, "instance", None)
        if contrato is not None:
            opcion["attrs"]["data-cliente"] = contrato.cliente.nombre
            opcion["attrs"]["data-linea"] = linea_de(contrato)
        return opcion


def linea_de(contrato):
    return contrato.linea_servicio.nombre if contrato.linea_servicio_id else "Sin asignar"


class EntregableForm(forms.Form):
    """Formulario con Poka-Yoke: los campos obligatorios salen de la plantilla TDR.

    Desde el Sprint 2 (RF-20) también pide los datos de recepción de HU-01: ID-TDR y fecha de recepción, que no puede
    ser futura ni posterior al plazo. Son obligatorios SIEMPRE (validación del servidor): una petición a la que le falta
    alguno, aunque no traiga la clave, se rechaza con el mensaje del Poka-Yoke. En la base de datos siguen admitiendo
    vacío, porque los entregables anteriores al Sprint 2 no los tienen.
    """

    CAMPOS_RECEPCION = ("id_tdr", "fecha_recepcion")

    contrato = forms.ModelChoiceField(
        queryset=Contrato.objects.none(), label="Contrato", widget=SelectorDeContrato(attrs={"data-reflejar": True}),
        error_messages={
            "required": "Falta elegir el contrato.",
            "invalid_choice": "Elija un contrato vigente de la lista (los contratos dados de baja no admiten entregables).",
        },
    )
    titulo = forms.CharField(label="Título", max_length=200, error_messages={"required": "Falta el título."})
    id_tdr = forms.CharField(
        label="ID-TDR", max_length=50, help_text="Identificador del TDR o de la solicitud del cliente.",
        error_messages={"required": "Falta el ID-TDR.", "max_length": "El ID-TDR no puede superar los 50 caracteres."},
    )
    fecha_recepcion = forms.DateField(
        label="Fecha de recepción", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        error_messages={"required": "Falta la fecha de recepción.", "invalid": "La fecha de recepción no es una fecha válida."},
    )
    plazo = forms.DateField(
        label="Plazo de entrega", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        error_messages={"required": "Falta el plazo de entrega.", "invalid": "El plazo no es una fecha válida."},
    )
    junior_asignado = forms.ModelChoiceField(
        queryset=Usuario.objects.none(), label="Junior asignado",
        error_messages={"required": "Falta asignar un junior."},
        help_text="Solo los juniors asignados al contrato.",
    )
    senior_revisor = forms.ModelChoiceField(
        queryset=Usuario.objects.none(), label="Senior revisor", required=False,
        empty_label="— El senior responsable del contrato —",
        error_messages={"invalid_choice": "Elija un senior de la lista."},
        help_text="Revisa y aprueba el entregable. Si no elige uno, será el senior responsable del contrato.",
    )

    AYUDA_POR_TIPO = {"numero": "Número", "fecha": "Fecha", "texto_largo": "Texto largo", "opcion": "Elija una opción"}

    def __init__(self, usuario, plantilla, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plantilla = plantilla
        self.fields["contrato"].queryset = contratos_para(usuario)
        self.fields["junior_asignado"].queryset = Usuario.objects.filter(rol=Usuario.Rol.JUNIOR, is_active=True)
        self.fields["senior_revisor"].queryset = Usuario.objects.filter(rol=Usuario.Rol.SENIOR, is_active=True)
        if not self.is_bound:
            self.fields["fecha_recepcion"].initial = timezone.localdate()
            if plantilla:
                self.fields["plazo"].initial = timezone.localdate() + datetime.timedelta(days=plantilla.plazo_dias_por_defecto)
        self.campos_dinamicos = []
        for c in (plantilla.campos_requeridos if plantilla else []):
            msg = {"required": f"Falta completar el campo «{c['etiqueta']}»."}
            tipo = c.get("tipo", "texto")
            ayuda = self.AYUDA_POR_TIPO.get(tipo, "")
            if tipo == "numero":
                campo = forms.DecimalField(label=c["etiqueta"], help_text=ayuda, error_messages={**msg, "invalid": f"«{c['etiqueta']}» debe ser un número."})
            elif tipo == "fecha":
                campo = forms.DateField(
                    label=c["etiqueta"], help_text=ayuda, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                    error_messages={**msg, "invalid": f"«{c['etiqueta']}» debe ser una fecha válida."},
                )
            elif tipo == "opcion":
                campo = forms.ChoiceField(
                    label=c["etiqueta"], help_text=ayuda,
                    choices=[("", "— Elija una opción —")] + [(o, o) for o in c.get("opciones", [])],
                    error_messages={**msg, "invalid_choice": f"Elija una opción válida para «{c['etiqueta']}»."},
                )
            elif tipo == "texto_largo":
                campo = forms.CharField(label=c["etiqueta"], help_text=ayuda, widget=forms.Textarea(attrs={"rows": 3}), error_messages=msg)
            else:
                campo = forms.CharField(label=c["etiqueta"], max_length=255, error_messages=msg)
            self.fields[c["nombre"]] = campo
            self.campos_dinamicos.append(c["nombre"])
        # Los errores se listan en el mismo orden en que se ven las secciones de la pantalla.
        self.order_fields(["contrato", "titulo", *self.CAMPOS_RECEPCION, "plazo", *self.campos_dinamicos,
                           "junior_asignado", "senior_revisor"])

    def _seccion(self, nombres):
        return [self[n] for n in nombres if n in self.fields]

    @property
    def campos_base(self):
        """Los campos del Sprint 1 que no dependen de la plantilla (se conservan para compatibilidad)."""
        return [self[n] for n in ("contrato", "titulo", "plazo", "junior_asignado", "senior_revisor")]

    @property
    def seccion_contrato(self):
        return self._seccion(("contrato", "titulo"))

    @property
    def seccion_recepcion(self):
        """«Recepción de la solicitud» del wireframe: ID-TDR, fecha de recepción y plazo de entrega."""
        return self._seccion((*self.CAMPOS_RECEPCION, "plazo"))

    @property
    def seccion_responsables(self):
        return self._seccion(("junior_asignado", "senior_revisor"))

    @property
    def campos_plantilla(self):
        return [self[n] for n in self.campos_dinamicos]

    def contrato_elegido(self):
        """El contrato elegido (o None), para mostrar su cliente y su línea de servicio en solo lectura.

        Sale del mismo queryset del campo, así que nunca revela un contrato que el usuario no puede elegir.
        """
        valor = self["contrato"].value()
        if not valor:
            return None
        try:
            return self.fields["contrato"].queryset.get(pk=valor)
        except (ValueError, TypeError, Contrato.DoesNotExist):
            return None

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
        # Las dos reglas de la recepción se revisan juntas para nombrar todo lo que está mal (p. ej. fechas invertidas).
        recepcion, plazo = datos.get("fecha_recepcion"), datos.get("plazo")
        if recepcion:
            if recepcion > timezone.localdate():
                self.add_error("fecha_recepcion", "La fecha de recepción no puede ser futura.")
            if plazo and recepcion > plazo:
                self.add_error("fecha_recepcion", "La fecha de recepción no puede ser posterior al plazo.")
        return datos

    def guardar(self, usuario):
        """Crea el entregable con sus datos de recepción. El código único lo asigna el modelo al guardarlo."""
        d = self.cleaned_data
        valores = {}
        for nombre in self.campos_dinamicos:
            v = d[nombre]
            valores[nombre] = v.isoformat() if isinstance(v, datetime.date) else (str(v) if not isinstance(v, str) else v)
        return Entregable.objects.create(
            contrato=d["contrato"], plantilla=self.plantilla, titulo=d["titulo"], datos=valores, plazo=d["plazo"],
            junior_asignado=d["junior_asignado"], creado_por=usuario,
            senior_revisor=d["senior_revisor"] or d["contrato"].senior_responsable,
            id_tdr=d["id_tdr"], fecha_recepcion=d["fecha_recepcion"],
        )


class AdjuntoForm(forms.Form):
    """Campos de la subida. La validación de extensión, tamaño y nombre la hace `archivos.validar_archivo` (común a otras
    apps), que el servicio `adjuntos` aplica al guardar."""

    tipo = forms.ChoiceField(
        choices=[("", "— Elija el tipo —")] + TipoAdjunto.choices, label="Tipo",
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # El navegador solo ofrece los formatos permitidos (el servidor igual los valida).
        self.fields["archivo"].widget.attrs["accept"] = ",".join(f".{e}" for e in adjuntos.extensiones_permitidas())


class ObservacionForm(forms.Form):
    tipo_error = forms.ChoiceField(
        choices=[("", "— Elija el tipo de error —")] + TipoError.choices, label="Tipo de error",
        error_messages={"required": "Elija el tipo de error.", "invalid_choice": "Elija un tipo de error válido."},
    )
    descripcion = forms.CharField(label="Descripción", widget=forms.Textarea(attrs={"rows": 3}))
