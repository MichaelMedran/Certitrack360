"""Vistas de incorporación y gestión de planes de incorporación (SDD del Sprint 2, §7.12, §8 y §10, RF-38: HU-15)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.conocimiento.models import Procedimiento
from apps.cuentas.models import Usuario
from apps.cuentas.permisos import solo_gestion
from apps.entregables.filtros import entero
from apps.repositorio.models import DocumentoRepositorio

from . import servicios
from .models import ActividadPlan, AvanceActividad, Incorporacion, PlanIncorporacion


@login_required
def incorporacion(request):
    """Pantalla `/incorporacion/` (GET y POST): muestra «Mi incorporación» al ingresante y «Vista del responsable»."""
    if request.method == "POST":
        accion = (request.POST.get("accion") or "").strip().lower()
        if not accion:
            if "confirmar" in request.POST or "incorporacion_id" in request.POST or "incorporacion" in request.POST:
                accion = "confirmar"
            else:
                accion = "avance"

        try:
            if accion in ("confirmar", "confirmar_finalizacion"):
                iid = entero(
                    request.POST.get("incorporacion")
                    or request.POST.get("incorporacion_id")
                    or request.POST.get("confirmar")
                )
                if iid is None:
                    raise Http404("No existe esa incorporación.")
                inc = get_object_or_404(Incorporacion.objects.select_related("plan", "ingresante", "responsable"), pk=iid)
                servicios.confirmar_finalizacion(inc, request.user)
                messages.success(
                    request,
                    f"Se confirmó la finalización del plan de incorporación de {inc.ingresante.nombre}.",
                )
                return redirect("incorporacion")

            if accion in ("avance", "marcar", "marcar_avance"):
                aid = entero(request.POST.get("avance") or request.POST.get("avance_id"))
                if aid is None:
                    raise Http404("No existe ese registro de avance.")
                avance = get_object_or_404(
                    AvanceActividad.objects.select_related("incorporacion", "actividad"),
                    pk=aid,
                )
                nuevo_estado = request.POST.get("estado") or AvanceActividad.Estado.COMPLETADA
                servicios.marcar_avance(avance, nuevo_estado, request.user)
                messages.success(
                    request,
                    f"Se actualizó la actividad «{avance.actividad.titulo}» a {avance.get_estado_display()}.",
                )
                destino = request.POST.get("next") or ""
                if destino == "inicio":
                    return redirect("inicio")
                return redirect("incorporacion")

            raise ValidationError("Acción no reconocida.")
        except ValidationError as exc:
            for m in exc.messages:
                messages.error(request, m)

    mis_incorporaciones = list(
        Incorporacion.objects.filter(ingresante=request.user)
        .select_related("plan", "responsable", "confirmada_por")
        .prefetch_related("avances__actividad__documento", "avances__actividad__procedimiento")
        .order_by("confirmada_en", "-creada_en", "-id")
    )
    mi_incorporacion = next((i for i in mis_incorporaciones if not i.confirmada), mis_incorporaciones[0] if mis_incorporaciones else None)

    qs_cargo = Incorporacion.objects.select_related("plan", "ingresante", "responsable", "confirmada_por").prefetch_related(
        "avances__actividad__documento", "avances__actividad__procedimiento"
    )
    if request.user.es_gerente_o_admin:
        a_cargo = list(qs_cargo.order_by("confirmada_en", "-creada_en", "-id"))
    else:
        a_cargo = list(qs_cargo.filter(responsable=request.user).order_by("confirmada_en", "-creada_en", "-id"))

    detalle_id = entero(request.GET.get("detalle"))
    detalle_inc = None
    if detalle_id is not None:
        detalle_inc = next((i for i in a_cargo if i.pk == detalle_id), None)

    return render(
        request,
        "equipo/incorporacion.html",
        {
            "mi_incorporacion": mi_incorporacion,
            "mis_incorporaciones": mis_incorporaciones,
            "incorporaciones_a_cargo": a_cargo,
            "detalle_incorporacion": detalle_inc,
            "estados_avance": AvanceActividad.Estado.choices,
        },
    )


def _plan_o_404(valor):
    pk = entero(valor)
    if pk is None:
        raise Http404("No existe ese plan de incorporación.")
    return get_object_or_404(PlanIncorporacion, pk=pk)


@solo_gestion
def planes(request):
    """Gestión de planes de incorporación y asignación a ingresantes (`/incorporacion/planes/`, gerente y admin: §8)."""
    editando = None
    if "plan" in request.GET or "editar" in request.GET:
        editando = _plan_o_404(request.GET.get("plan") or request.GET.get("editar"))

    if request.method == "POST":
        accion = (request.POST.get("accion") or "").strip().lower()
        if not accion:
            if "ingresante" in request.POST and "responsable" in request.POST:
                accion = "asignar"
            elif "titulo_actividad" in request.POST or "actividad_titulo" in request.POST:
                accion = "agregar_actividad"
            else:
                accion = "guardar_plan"

        try:
            if accion in ("guardar_plan", "plan"):
                pid = request.POST.get("plan_id") or request.POST.get("plan")
                if pid not in (None, ""):
                    editando = _plan_o_404(pid)
                activo_val = request.POST.get("activo", "1") not in ("0", "false", "no", "off")
                plan = servicios.guardar_plan(
                    request.user,
                    nombre=request.POST.get("nombre", ""),
                    rol=request.POST.get("rol", Usuario.Rol.JUNIOR),
                    puesto=request.POST.get("puesto", ""),
                    activo=activo_val,
                    plan=editando,
                )
                # Si también se envió una actividad inicial en el mismo formulario
                titulo_act = (request.POST.get("actividad_titulo") or request.POST.get("titulo_actividad") or "").strip()
                if titulo_act:
                    servicios.agregar_actividad(
                        request.user,
                        plan,
                        titulo=titulo_act,
                        semana=request.POST.get("semana", 1),
                        orden=request.POST.get("orden"),
                        documento=request.POST.get("documento"),
                        procedimiento=request.POST.get("procedimiento"),
                        enlace_interno=request.POST.get("enlace_interno", ""),
                        etiqueta_recurso=request.POST.get("etiqueta_recurso", ""),
                        rol_responsable=request.POST.get("rol_responsable", "Senior asignado"),
                        como_se_comprueba=request.POST.get("como_se_comprueba", ""),
                    )
                messages.success(request, f"Se guardó el plan «{plan.nombre}».")
                return redirect(f"{reverse('incorporacion_planes')}?plan={plan.pk}")

            if accion == "agregar_actividad":
                plan = _plan_o_404(request.POST.get("plan") or request.POST.get("plan_id"))
                act = servicios.agregar_actividad(
                    request.user,
                    plan,
                    titulo=request.POST.get("titulo") or request.POST.get("actividad_titulo") or request.POST.get("titulo_actividad", ""),
                    semana=request.POST.get("semana", 1),
                    orden=request.POST.get("orden"),
                    descripcion=request.POST.get("descripcion", ""),
                    documento=request.POST.get("documento"),
                    procedimiento=request.POST.get("procedimiento"),
                    enlace_interno=request.POST.get("enlace_interno", ""),
                    etiqueta_recurso=request.POST.get("etiqueta_recurso", ""),
                    rol_responsable=request.POST.get("rol_responsable", "Senior asignado"),
                    como_se_comprueba=request.POST.get("como_se_comprueba", ""),
                )
                messages.success(request, f"Se agregó la actividad «{act.titulo}» al plan «{plan.nombre}».")
                return redirect(f"{reverse('incorporacion_planes')}?plan={plan.pk}")

            if accion == "quitar_actividad":
                aid = entero(request.POST.get("actividad") or request.POST.get("actividad_id"))
                act = get_object_or_404(ActividadPlan, pk=aid)
                plan_pk = act.plan_id
                if not act.avances.exists():
                    act.delete()
                    messages.success(request, "Se quitó la actividad del plan.")
                else:
                    messages.error(request, "No se puede eliminar una actividad que ya tiene avances registrados.")
                return redirect(f"{reverse('incorporacion_planes')}?plan={plan_pk}")

            if accion in ("asignar", "asignar_plan"):
                inc = servicios.asignar_plan(
                    request.POST.get("plan") or request.POST.get("plan_id"),
                    request.POST.get("ingresante"),
                    request.POST.get("responsable"),
                    fecha_inicio=request.POST.get("fecha_inicio"),
                    autor=request.user,
                )
                messages.success(
                    request,
                    f"Se asignó el plan «{inc.plan.nombre}» a {inc.ingresante.nombre}.",
                )
                return redirect("incorporacion_planes")

            raise ValidationError("Acción no reconocida.")
        except ValidationError as exc:
            for m in exc.messages:
                messages.error(request, m)

    planes_qs = list(
        PlanIncorporacion.objects.prefetch_related(
            "actividades__documento",
            "actividades__procedimiento",
        ).order_by("nombre", "-id")
    )
    if editando is None and planes_qs:
        editando = planes_qs[0]

    usuarios_activos = list(Usuario.objects.filter(is_active=True).order_by("first_name", "last_name", "username"))
    responsables_posibles = [u for u in usuarios_activos if u.rol in (Usuario.Rol.SENIOR, Usuario.Rol.GERENTE, Usuario.Rol.ADMIN)]

    return render(
        request,
        "equipo/planes.html",
        {
            "planes": planes_qs,
            "editando": editando,
            "roles": Usuario.Rol.choices,
            "usuarios": usuarios_activos,
            "responsables": responsables_posibles,
            "procedimientos": Procedimiento.objects.filter(vigente=True).order_by("titulo"),
            "documentos": DocumentoRepositorio.objects.filter(activo=True).order_by("titulo"),
            "incorporaciones": Incorporacion.objects.select_related("plan", "ingresante", "responsable", "confirmada_por").order_by("-creada_en", "-id")[:30],
        },
    )
