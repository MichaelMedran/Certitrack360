import datetime
import json

from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.clientes.models import Contrato, PlantillaTDR
from apps.cuentas.models import Usuario
from apps.entregables import archivos
from apps.entregables.filtros import entero

from . import servicios
from .models import FichaLevantamiento, ItemFicha
from .visibilidad import contratos_para_ficha

FILA_ITEM_VACIA = {
    "nombre": "",
    "plantilla": "",
    "frecuencia": ItemFicha.Frecuencia.MENSUAL,
    "primera_fecha": "",
    "hasta": "",
    "junior": "",
    "senior": "",
    "datos": {},
    "errores": [],
}


def _en(lista, i):
    return lista[i] if i < len(lista) else ""


def _parsear_fecha(valor):
    texto = (valor or "").strip()
    if not texto:
        return None
    return datetime.date.fromisoformat(texto)


class FichaLevantamientoForm(forms.Form):
    """Formulario de alta y edición de una ficha de levantamiento en borrador (RF-30: HU-14 y HU-06)."""

    contrato = forms.ModelChoiceField(
        queryset=Contrato.objects.none(),
        label="Contrato",
        empty_label="— Elija el contrato —",
        error_messages={
            "required": "Falta elegir el contrato.",
            "invalid_choice": "Elija un contrato vigente de la lista.",
        },
    )
    id_tdr = forms.CharField(
        label="ID-TDR",
        max_length=50,
        error_messages={
            "required": "Falta el ID-TDR.",
            "max_length": "El ID-TDR no puede superar los 50 caracteres.",
        },
    )
    archivo_tdr = forms.FileField(
        label="Archivo del TDR",
        required=False,
        error_messages={
            "required": "Falta adjuntar el archivo del TDR.",
            "missing": "Falta adjuntar el archivo del TDR.",
            "empty": "El archivo del TDR está vacío.",
            "invalid": "No se pudo leer el archivo del TDR.",
        },
    )
    requerimientos = forms.CharField(
        label="Requerimientos del servicio",
        widget=forms.Textarea(attrs={"rows": 3}),
        error_messages={"required": "Falta indicar los requerimientos del servicio."},
    )
    formatos = forms.CharField(label="Formatos a presentar", max_length=255, required=False)
    frecuencia_reportes = forms.CharField(label="Frecuencia de reportes", max_length=100, required=False)
    penalidades = forms.CharField(
        label="Penalidades por incumplimiento",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    responsable = forms.ModelChoiceField(
        queryset=Usuario.objects.none(),
        label="Responsable",
        empty_label="— Elija el responsable —",
        error_messages={
            "required": "Falta elegir el responsable de la ficha.",
            "invalid_choice": "Elija un responsable válido.",
        },
    )
    documentos_disponibles = forms.CharField(
        label="Documentos disponibles",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    documentos_faltantes = forms.CharField(
        label="Documentos faltantes",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    formato_esperado = forms.CharField(label="Formato esperado", max_length=150, required=False)
    fecha_limite = forms.DateField(
        label="Fecha límite",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        error_messages={"invalid": "La fecha límite no es una fecha válida."},
    )
    estado_documental = forms.ChoiceField(
        label="Estado documental",
        choices=FichaLevantamiento.EstadoDocumental.choices,
        required=False,
        initial=FichaLevantamiento.EstadoDocumental.ABIERTO,
        error_messages={"invalid_choice": "Elija un estado documental válido."},
    )

    def __init__(self, usuario, *args, instance=None, contrato_inicial=None, **kwargs):
        self.usuario = usuario
        self.instance = instance
        if not args and "initial" not in kwargs and instance is not None:
            kwargs["initial"] = {
                "contrato": instance.contrato_id,
                "id_tdr": instance.id_tdr,
                "requerimientos": instance.requerimientos,
                "formatos": instance.formatos,
                "frecuencia_reportes": instance.frecuencia_reportes,
                "penalidades": instance.penalidades,
                "responsable": instance.responsable_id,
                "documentos_disponibles": instance.documentos_disponibles,
                "documentos_faltantes": instance.documentos_faltantes,
                "formato_esperado": instance.formato_esperado,
                "fecha_limite": instance.fecha_limite,
                "estado_documental": instance.estado_documental,
            }
        elif not args and "initial" not in kwargs and contrato_inicial is not None:
            kwargs["initial"] = {"contrato": contrato_inicial.pk, "responsable": usuario.pk}
        super().__init__(*args, **kwargs)
        qs_contratos = contratos_para_ficha(usuario)
        if instance is not None and instance.contrato_id:
            qs_contratos = (qs_contratos.distinct() | Contrato.objects.filter(pk=instance.contrato_id).distinct()).distinct()
        self.fields["contrato"].queryset = qs_contratos
        self.fields["responsable"].queryset = Usuario.objects.filter(is_active=True).order_by(
            "first_name", "last_name", "username"
        )
        self.fields["archivo_tdr"].widget.attrs["accept"] = ",".join(f".{e}" for e in archivos.extensiones_permitidas())
        self.nombre_archivo_saneado = instance.nombre_archivo_tdr if instance else ""
        self.items_limpios = []
        self.filas = self._construir_filas()

    def _extraer_dato_item(self, i, plantilla_pk, clave, datos_json_fila):
        """Obtiene el valor crudo de un campo de plantilla para la fila `i`, admitiendo los distintos formatos de envío."""
        if isinstance(datos_json_fila, dict) and clave in datos_json_fila:
            return datos_json_fila[clave]
        for candidato in (
            self.data.get(f"item_dato_{i}_{clave}"),
            _en(self.data.getlist(f"item_dato_{plantilla_pk}_{clave}"), i) if plantilla_pk else None,
            _en(self.data.getlist(f"item_dato_{clave}"), i),
            _en(self.data.getlist(clave), i),
        ):
            if candidato is not None and str(candidato).strip() != "":
                return candidato
        return ""

    def _construir_filas(self):
        if self.is_bound:
            nombres = self.data.getlist("item_nombre")
            plantillas = self.data.getlist("item_plantilla")
            frecuencias = self.data.getlist("item_frecuencia")
            primeras = self.data.getlist("item_primera_fecha")
            hastas = self.data.getlist("item_hasta")
            juniors = self.data.getlist("item_junior")
            seniors = self.data.getlist("item_senior")
            datos_json = self.data.getlist("item_datos")
            total = max(
                len(nombres),
                len(plantillas),
                len(frecuencias),
                len(primeras),
                len(hastas),
                len(juniors),
                len(seniors),
                len(datos_json),
            )
            filas = []
            plantillas_bd = PlantillaTDR.objects.in_bulk(
                [pid for pid in (entero(p) for p in plantillas) if pid is not None]
            )
            for i in range(total):
                raw_json = _en(datos_json, i)
                parsed_json = {}
                if raw_json:
                    try:
                        cargado = json.loads(raw_json)
                        if isinstance(cargado, dict):
                            parsed_json = cargado
                    except ValueError:
                        parsed_json = {}
                pid = entero(_en(plantillas, i))
                plantilla_obj = plantillas_bd.get(pid)
                datos_fila = dict(parsed_json)
                if plantilla_obj:
                    for c in plantilla_obj.campos_requeridos:
                        clave = c["nombre"]
                        datos_fila[clave] = self._extraer_dato_item(i, plantilla_obj.pk, clave, parsed_json)
                filas.append(
                    {
                        "nombre": _en(nombres, i),
                        "plantilla": str(pid) if pid is not None else _en(plantillas, i),
                        "frecuencia": _en(frecuencias, i) or ItemFicha.Frecuencia.MENSUAL,
                        "primera_fecha": _en(primeras, i),
                        "hasta": _en(hastas, i),
                        "junior": _en(juniors, i),
                        "senior": _en(seniors, i),
                        "datos": datos_fila,
                        "errores": [],
                    }
                )
            return filas or [dict(FILA_ITEM_VACIA)]
        if self.instance is not None and self.instance.pk:
            existentes = [
                {
                    "nombre": it.nombre,
                    "plantilla": str(it.plantilla_id),
                    "frecuencia": it.frecuencia,
                    "primera_fecha": it.primera_fecha.isoformat() if it.primera_fecha else "",
                    "hasta": it.hasta.isoformat() if it.hasta else "",
                    "junior": str(it.junior_id),
                    "senior": str(it.senior_id) if it.senior_id else "",
                    "datos": dict(it.datos or {}),
                    "errores": [],
                }
                for it in self.instance.items.all()
            ]
            return existentes or [dict(FILA_ITEM_VACIA)]
        return [dict(FILA_ITEM_VACIA)]

    def clean_id_tdr(self):
        valor = (self.cleaned_data.get("id_tdr") or "").strip()
        if not valor:
            raise ValidationError("Falta el ID-TDR.")
        return valor

    def clean_requerimientos(self):
        valor = (self.cleaned_data.get("requerimientos") or "").strip()
        if not valor:
            raise ValidationError("Falta indicar los requerimientos del servicio.")
        return valor

    def clean_archivo_tdr(self):
        archivo = self.cleaned_data.get("archivo_tdr")
        tiene_previo = bool(self.instance and self.instance.pk and self.instance.archivo_tdr)
        if not archivo:
            if not tiene_previo:
                raise ValidationError("Falta adjuntar el archivo del TDR.")
            return None
        self.nombre_archivo_saneado = archivos.validar_archivo(archivo)
        return archivo

    def clean_estado_documental(self):
        valor = self.cleaned_data.get("estado_documental")
        return valor or FichaLevantamiento.EstadoDocumental.ABIERTO

    def clean(self):
        datos = super().clean()
        contrato = datos.get("contrato")
        if contrato and (not contrato.activo or not contrato.cliente.activo):
            self.add_error("contrato", "El contrato elegido está dado de baja y no admite entregables.")

        juniors_contrato = set(contrato.juniors.values_list("pk", flat=True)) if contrato else set()
        items_limpios = []
        errores_items = []

        for idx, fila in enumerate(self.filas, start=1):
            nombre = (fila["nombre"] or "").strip()
            pid_raw = (fila["plantilla"] or "").strip()
            primera_raw = (fila["primera_fecha"] or "").strip()
            hasta_raw = (fila["hasta"] or "").strip()
            junior_raw = (fila["junior"] or "").strip()
            senior_raw = (fila["senior"] or "").strip()
            frec = (fila["frecuencia"] or "").strip()

            # Una fila totalmente vacía se ignora.
            if not any([nombre, pid_raw, primera_raw, hasta_raw, junior_raw, fila.get("datos")]):
                continue

            ref = f"«{nombre}»" if nombre else f"el entregable n.º {idx}"
            errores_fila = []

            if not nombre:
                errores_fila.append(f"Falta el nombre del entregable en la fila {idx}.")

            pid = entero(pid_raw)
            plantilla = PlantillaTDR.objects.select_related("cliente").filter(pk=pid).first() if pid is not None else None
            if plantilla is None:
                errores_fila.append(f"En {ref} falta elegir la plantilla.")
            elif contrato and plantilla.cliente_id and plantilla.cliente_id != contrato.cliente_id:
                errores_fila.append(f"En {ref} la plantilla «{plantilla.nombre}» pertenece a otro cliente.")

            if frec not in ItemFicha.Frecuencia.values:
                errores_fila.append(f"En {ref} falta elegir la frecuencia.")

            primera_fecha = None
            if not primera_raw:
                errores_fila.append(f"En {ref} falta la primera fecha.")
            else:
                try:
                    primera_fecha = _parsear_fecha(primera_raw)
                except ValueError:
                    errores_fila.append(f"En {ref} la primera fecha no es una fecha válida.")

            hasta = None
            if hasta_raw:
                try:
                    hasta = _parsear_fecha(hasta_raw)
                except ValueError:
                    errores_fila.append(f"En {ref} la fecha final («Hasta») no es una fecha válida.")
                else:
                    if primera_fecha and hasta < primera_fecha:
                        errores_fila.append(f"En {ref} la fecha final («Hasta») no puede ser anterior a la primera fecha.")
            elif (
                primera_fecha
                and contrato
                and frec in ItemFicha.Frecuencia.values
                and frec != ItemFicha.Frecuencia.UNICA
                and contrato.fecha_fin < primera_fecha
            ):
                errores_fila.append(f"En {ref} la primera fecha es posterior al fin del contrato.")

            jid = entero(junior_raw)
            junior = (
                Usuario.objects.filter(pk=jid, rol=Usuario.Rol.JUNIOR, is_active=True).first()
                if jid is not None
                else None
            )
            if junior is None:
                errores_fila.append(f"En {ref} falta asignar un junior.")
            elif contrato and junior.pk not in juniors_contrato:
                errores_fila.append(f"En {ref} el junior {junior.nombre} no está asignado al contrato elegido.")

            senior = None
            if senior_raw:
                sid = entero(senior_raw)
                senior = (
                    Usuario.objects.filter(pk=sid, rol=Usuario.Rol.SENIOR, is_active=True).first()
                    if sid is not None
                    else None
                )
                if senior is None:
                    errores_fila.append(f"En {ref} elija un senior válido.")

            datos_limpios = {}
            if plantilla is not None:
                for campo in plantilla.campos_requeridos:
                    clave = campo["nombre"]
                    crudo = (fila.get("datos") or {}).get(clave, "")
                    try:
                        datos_limpios[clave] = servicios.validar_dato_campo(nombre or f"fila {idx}", campo, crudo)
                    except ValidationError as exc:
                        errores_fila.extend(exc.messages)

            fila["errores"] = errores_fila
            errores_items.extend(errores_fila)
            if not errores_fila:
                items_limpios.append(
                    {
                        "nombre": nombre,
                        "plantilla": plantilla,
                        "frecuencia": frec,
                        "primera_fecha": primera_fecha,
                        "hasta": hasta,
                        "junior": junior,
                        "senior": senior,
                        "datos": datos_limpios,
                    }
                )

        if not items_limpios and not errores_items:
            errores_items.append("Debe registrar al menos un entregable en la ficha.")

        for err in errores_items:
            self.add_error(None, err)

        self.items_limpios = items_limpios
        return datos

    @transaction.atomic
    def guardar(self, usuario):
        d = self.cleaned_data
        ficha = self.instance or FichaLevantamiento(creada_por=usuario)
        ficha.contrato = d["contrato"]
        ficha.id_tdr = d["id_tdr"]
        ficha.requerimientos = d["requerimientos"]
        ficha.formatos = (d.get("formatos") or "").strip()
        ficha.frecuencia_reportes = (d.get("frecuencia_reportes") or "").strip()
        ficha.penalidades = (d.get("penalidades") or "").strip()
        ficha.responsable = d["responsable"]
        ficha.documentos_disponibles = (d.get("documentos_disponibles") or "").strip()
        ficha.documentos_faltantes = (d.get("documentos_faltantes") or "").strip()
        ficha.formato_esperado = (d.get("formato_esperado") or "").strip()
        ficha.fecha_limite = d.get("fecha_limite")
        ficha.estado_documental = d.get("estado_documental") or FichaLevantamiento.EstadoDocumental.ABIERTO
        archivo = d.get("archivo_tdr")
        if archivo is not None:
            archivo.name = self.nombre_archivo_saneado
            ficha.archivo_tdr = archivo
            ficha.nombre_archivo_tdr = self.nombre_archivo_saneado
        ficha.save()
        ficha.items.all().delete()
        for item_data in self.items_limpios:
            ItemFicha.objects.create(ficha=ficha, **item_data)
        return ficha


class EstadoDocumentalForm(forms.Form):
    """Formulario para actualizar el estado documental actual después de confirmar la ficha (HU-06)."""

    documentos_disponibles = forms.CharField(
        label="Documentos disponibles",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    documentos_faltantes = forms.CharField(
        label="Documentos faltantes",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    formato_esperado = forms.CharField(label="Formato esperado", max_length=150, required=False)
    fecha_limite = forms.DateField(
        label="Fecha límite",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        error_messages={"invalid": "La fecha límite no es una fecha válida."},
    )
    estado_documental = forms.ChoiceField(
        label="Estado documental",
        choices=FichaLevantamiento.EstadoDocumental.choices,
        error_messages={
            "required": "Elija un estado documental válido.",
            "invalid_choice": "Elija un estado documental válido.",
        },
    )

    def __init__(self, ficha, *args, **kwargs):
        if not args and "initial" not in kwargs:
            kwargs["initial"] = {
                "documentos_disponibles": ficha.documentos_disponibles,
                "documentos_faltantes": ficha.documentos_faltantes,
                "formato_esperado": ficha.formato_esperado,
                "fecha_limite": ficha.fecha_limite,
                "estado_documental": ficha.estado_documental,
            }
        super().__init__(*args, **kwargs)
