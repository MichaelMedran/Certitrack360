"""Gestión de clientes, contratos, plantillas, personal y líneas de servicio (solo Gerente y Admin)."""
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.db.models.functions import Lower
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.alertas import whatsapp
from apps.cuentas.models import Ausencia, Usuario
from apps.cuentas.permisos import solo_gestion
from apps.entregables import personal as personal_srv
from apps.entregables.filtros import entero
from apps.entregables.models import Entregable, ResponsableApoyo
from apps.urgencias import servicios as urgencias_srv

from .forms import FILA_VACIA, TIPOS_CAMPO_ETIQUETAS, ClienteForm, ContratoForm, LineaServicioForm, PlantillaForm
from .models import Cliente, Contrato, LineaServicio, PlantillaTDR

ENTIDADES = {
    "clientes": {"modelo": Cliente, "form": ClienteForm, "titulo": "Clientes", "nuevo": "Nuevo cliente",
                 "guardado": "Se guardó el cliente."},
    "contratos": {"modelo": Contrato, "form": ContratoForm, "titulo": "Contratos", "nuevo": "Nuevo contrato",
                  "guardado": "Se guardó el contrato."},
    "plantillas": {"modelo": PlantillaTDR, "form": PlantillaForm, "titulo": "Plantillas", "nuevo": "Nueva plantilla",
                   "guardado": "Se guardó la plantilla."},
}


def _config(entidad):
    if entidad not in ENTIDADES:
        raise Http404
    return ENTIDADES[entidad]


@solo_gestion
def gestion(request):
    """Acceso común de «Gestión»: lleva a la primera pestaña."""
    return redirect("adm_lista", entidad="clientes")


@solo_gestion
def lista(request, entidad):
    config = _config(entidad)
    modelo = config["modelo"]
    qs = modelo.objects.all()
    if modelo is Contrato:
        qs = qs.select_related("cliente", "senior_responsable", "linea_servicio").prefetch_related("juniors")
    if modelo is PlantillaTDR:
        qs = qs.select_related("cliente")
    return render(request, "clientes/lista.html", {"entidad": entidad, "config": config, "objetos": qs})


@solo_gestion
def editar(request, entidad, pk=None):
    config = _config(entidad)
    objeto = get_object_or_404(config["modelo"], pk=pk) if pk else None
    form = config["form"](request.POST or None, instance=objeto)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, config["guardado"])
        return redirect("adm_lista", entidad=entidad)
    return render(request, "clientes/form.html", {
        "form": form, "entidad": entidad, "config": config, "objeto": objeto,
        "tipos_campo": TIPOS_CAMPO_ETIQUETAS, "fila_vacia": FILA_VACIA,
    })


def _linea_o_404(valor):
    """La línea de servicio con ese id, o 404 si el id no es un número válido (o está fuera de rango) o no existe."""
    pk = entero(valor)
    if pk is None:
        raise Http404("No existe esa línea de servicio.")
    return get_object_or_404(LineaServicio, pk=pk)


@solo_gestion  # sin sesión: al ingreso; junior y senior: 403, igual que el resto de Gestión
def lineas_servicio(request):
    """Pestaña «Líneas de servicio» (SDD del Sprint 2, RF-24; ruta /lineas-servicio/, GET y POST).

    GET: el catálogo y, con ?nueva o ?editar=<id>, el formulario de alta o de edición.
    POST: guarda una línea nueva o, si trae «linea», la edita (renombrar, activar o desactivar). No hay borrado: la baja
    es lógica y una línea en uso está protegida también en la base de datos.
    """
    editando, form = None, None
    if request.method == "POST":
        if "linea" in request.POST:  # edición: un id mal escrito o inexistente es 404 (nunca crea otra línea)
            editando = _linea_o_404(request.POST.get("linea"))
        form = LineaServicioForm(request.POST, instance=editando)
        if form.is_valid():
            linea = form.save()
            accion = "Se guardaron los cambios de" if editando else "Se creó"
            messages.success(request, f"{accion} la línea de servicio «{linea.nombre}».")
            return redirect("lineas_servicio")
    else:
        if "editar" in request.GET:
            editando = _linea_o_404(request.GET.get("editar"))
            form = LineaServicioForm(instance=editando)
        elif "nueva" in request.GET:
            form = LineaServicioForm()
    # Con GROUP BY Django no aplica el orden del modelo: se pide de nuevo, alfabético.
    lineas = LineaServicio.objects.annotate(n_contratos=Count("contratos")).order_by(Lower("nombre"))
    return render(request, "clientes/lineas.html", {
        "entidad": "lineas", "lineas": lineas, "form": form, "editando": editando,
    })


@solo_gestion  # sin sesión: al ingreso; junior y senior: 403 (§7.6, §8, s2-personal.html)
def personal(request):
    """Pestaña «Personal» de Gestión (SDD del Sprint 2, RF-31; ruta /personal/, GET y POST).

    Muestra los colaboradores con su rol, puesto, entregables activos, vencimientos en 7 días, ausencias próximas y
    carga (con «Sobrecarga» desde `CARGA_MAXIMA_ACTIVOS`); permite registrar o eliminar ausencias, editar el puesto y
    consultar o reasignar las asignaciones de un colaborador.
    """
    conflicto_personal = None
    entregable_reasignar = None
    rol_reasignar = "junior"

    if request.method == "POST":
        accion = request.POST.get("accion") or (
            "reasignar" if ("entregable" in request.POST and ("usuario" in request.POST or "nuevo_usuario" in request.POST))
            else "ausencia"
        )
        try:
            if accion in ("ausencia", "registrar_ausencia"):
                aus = personal_srv.registrar_ausencia(
                    request.POST.get("usuario")
                    or request.POST.get("usuario_ausencia")
                    or request.POST.get("colaborador"),
                    request.POST.get("desde"),
                    request.POST.get("hasta"),
                    request.POST.get("motivo", ""),
                    request.user,
                )
                messages.success(
                    request,
                    f"Se registró la ausencia de {aus.usuario.nombre} ({aus.desde:%d/%m/%Y} a {aus.hasta:%d/%m/%Y}).",
                )
                return redirect("personal")
            if accion == "eliminar_ausencia":
                aid = entero(request.POST.get("ausencia_id") or request.POST.get("ausencia"))
                ausencia = get_object_or_404(Ausencia, pk=aid)
                ausencia.delete()
                messages.success(request, "Se eliminó la ausencia.")
                return redirect("personal")
            if accion in ("puesto", "actualizar_puesto"):
                uid = entero(
                    request.POST.get("usuario")
                    or request.POST.get("usuario_id")
                    or request.POST.get("colaborador")
                )
                u = get_object_or_404(Usuario, pk=uid)
                u.puesto = (request.POST.get("puesto") or "").strip()[:100]
                campos = ["puesto"]
                if "celular" in request.POST:
                    u.celular = whatsapp.normalizar_celular(request.POST.get("celular"))
                    campos.append("celular")
                u.save(update_fields=campos)
                messages.success(request, f"Se actualizaron los datos de {u.nombre}.")
                return redirect(f"{reverse('personal')}?colaborador={u.pk}")
            if accion == "reasignar":
                eid = entero(request.POST.get("entregable") or request.POST.get("entregable_id"))
                entregable_reasignar = get_object_or_404(Entregable, pk=eid)
                rol_reasignar = request.POST.get("rol") or request.POST.get("rol_destino") or "junior"
                nuevo_uid = request.POST.get("usuario") or request.POST.get("nuevo_usuario")
                motivo = request.POST.get("motivo", "")
                confirmar = request.POST.get("confirmar") in ("1", "true", "si", "on")
                res = personal_srv.reasignar_principal(
                    entregable_reasignar, rol_reasignar, nuevo_uid, request.user, motivo=motivo, confirmar=confirmar
                )
                if not res.confirmado:
                    conflicto_personal = {
                        "entregable": entregable_reasignar,
                        "rol": rol_reasignar,
                        "usuario": entero(nuevo_uid),
                        "motivo": motivo,
                        "conflictos": res.conflictos,
                    }
                else:
                    messages.success(request, f"Se reasignó {entregable_reasignar.referencia}.")
                    return redirect("personal")
            elif accion == "quitar_apoyo":
                apoyo_id = entero(request.POST.get("apoyo_id") or request.POST.get("apoyo"))
                apoyo = get_object_or_404(ResponsableApoyo.objects.select_related("entregable", "usuario"), pk=apoyo_id)
                personal_srv.quitar_apoyo(apoyo, request.user)
                messages.success(request, f"Se quitó a {apoyo.usuario.nombre} como apoyo.")
                return redirect("personal")
            elif accion == "guardia":  # marca «de guardia» (RF-43, D4): solo gerente y admin, que son quienes llegan aquí
                u = get_object_or_404(Usuario, pk=entero(request.POST.get("usuario")))
                urgencias_srv.marcar_guardia(request.user, u, request.POST.get("de_guardia") == "1")
                messages.success(request, f"{u.nombre} " + ("quedó de guardia." if u.de_guardia else "dejó la guardia."))
                return redirect("personal")
            else:
                raise ValidationError("Acción no reconocida.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))

    rol = (request.GET.get("rol") or "").strip()
    if rol not in Usuario.Rol.values:
        rol = ""
    q = (request.GET.get("q") or request.GET.get("buscar") or "").strip()[:100]

    colaboradores = personal_srv.resumen_colaboradores(rol=rol, q=q)

    if entregable_reasignar is None and "reasignar" in request.GET:
        eid = entero(request.GET.get("reasignar"))
        if eid is not None:
            entregable_reasignar = Entregable.objects.filter(pk=eid).first()
            rol_reasignar = "senior" if request.GET.get("rol") == "senior" else "junior"

    colaborador_id = entero(request.GET.get("colaborador"))
    seleccionado = None
    if colaborador_id is not None:
        seleccionado = Usuario.objects.filter(pk=colaborador_id, is_active=True).first()
    if seleccionado is None and entregable_reasignar is not None:
        seleccionado = (
            entregable_reasignar.senior_revisor if rol_reasignar == "senior" else entregable_reasignar.junior_asignado
        )
    if seleccionado is None and colaboradores:
        con_activos = [f["usuario"] for f in colaboradores if f["activos"] > 0]
        seleccionado = con_activos[0] if con_activos else colaboradores[0]["usuario"]

    asignaciones = personal_srv.asignaciones_de(seleccionado) if seleccionado else []

    todos_usuarios = list(
        Usuario.objects.filter(is_active=True).order_by("first_name", "last_name", "username")
    )
    juniors_activos = [u for u in todos_usuarios if u.rol == Usuario.Rol.JUNIOR]
    seniors_activos = [u for u in todos_usuarios if u.rol == Usuario.Rol.SENIOR]

    return render(request, "clientes/personal.html", {
        "entidad": "personal",
        "colaboradores": colaboradores,
        "todos_usuarios": todos_usuarios,
        "juniors_activos": juniors_activos,
        "seniors_activos": seniors_activos,
        "roles": Usuario.Rol.choices,
        "filtro_rol": rol,
        "filtro_q": q,
        "carga_maxima": settings.CARGA_MAXIMA_ACTIVOS,
        "whatsapp_activo": whatsapp.activo(),
        "seleccionado": seleccionado,
        "asignaciones": asignaciones,
        "entregable_reasignar": entregable_reasignar,
        "rol_reasignar": rol_reasignar,
        "conflicto_personal": conflicto_personal,
    })
