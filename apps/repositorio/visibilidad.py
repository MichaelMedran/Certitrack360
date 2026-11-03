"""Visibilidad y permisos del repositorio de plantillas y ejemplos anonimizados (SDD del Sprint 2, §7.9 y §8)."""
from django.db.models import Q

from apps.clientes.models import Cliente

from .models import DocumentoRepositorio


def clientes_visibles_repositorio(usuario):
    """Clientes cuyas plantillas del repositorio puede ver el usuario (§7.9).

    - Gerente y Admin: todos los clientes.
    - Senior: clientes donde es `senior_responsable` de un contrato o `senior_revisor` de un entregable.
    - Junior: clientes donde está asignado a un contrato activo (`contratos__activo=True, contratos__juniors=usuario`).
    """
    if not getattr(usuario, "is_authenticated", False):
        return Cliente.objects.none()
    if usuario.es_gerente_o_admin:
        return Cliente.objects.all()
    if usuario.es_senior:
        return Cliente.objects.filter(
            Q(contratos__senior_responsable=usuario) | Q(contratos__entregables__senior_revisor=usuario)
        ).distinct()
    return Cliente.objects.filter(contratos__activo=True, contratos__juniors=usuario).distinct()


def documentos_visibles(usuario, incluir_inactivos=False):
    """Queryset base de `DocumentoRepositorio` visible para el usuario (§7.9).

    - Plantillas genéricas (`PLANTILLA_CLIENTE` con `cliente__isnull=True`) y ejemplos anonimizados
      (`EJEMPLO_ANONIMIZADO`) son visibles para todos los roles.
    - Plantillas de un cliente específico (`PLANTILLA_CLIENTE` con `cliente` asignado): según `clientes_visibles_repositorio`.
    """
    if not getattr(usuario, "is_authenticated", False):
        return DocumentoRepositorio.objects.none()
    qs = DocumentoRepositorio.objects.all()
    if not (incluir_inactivos and usuario.es_gerente_o_admin):
        qs = qs.filter(activo=True)
    if usuario.es_gerente_o_admin:
        return qs
    clientes_ids = clientes_visibles_repositorio(usuario).values("pk")
    return qs.filter(
        Q(categoria=DocumentoRepositorio.Categoria.EJEMPLO_ANONIMIZADO)
        | Q(categoria=DocumentoRepositorio.Categoria.PLANTILLA_CLIENTE, cliente__isnull=True)
        | Q(categoria=DocumentoRepositorio.Categoria.PLANTILLA_CLIENTE, cliente_id__in=clientes_ids)
    ).distinct()


def clientes_para_cargar_plantilla(usuario):
    """Clientes para los que el usuario puede cargar una plantilla."""
    if not getattr(usuario, "is_authenticated", False):
        return Cliente.objects.none()
    if usuario.es_gerente_o_admin:
        return Cliente.objects.filter(activo=True)
    if usuario.es_senior:
        return clientes_visibles_repositorio(usuario).filter(activo=True)
    return Cliente.objects.none()


def puede_mostrar_boton_cargar_plantilla(usuario):
    """True si el usuario puede abrir el formulario de carga de plantillas."""
    if not getattr(usuario, "is_authenticated", False):
        return False
    if usuario.es_gerente_o_admin:
        return True
    if usuario.es_senior:
        return clientes_visibles_repositorio(usuario).exists()
    return False


def puede_cargar_plantilla(usuario, cliente=None):
    """Permiso para cargar una plantilla de cliente (o genérica si `cliente` es `None`, §7.9).

    - Junior: No (403).
    - Senior: Sí, para sus clientes (403 si es de otro cliente o genérica).
    - Gerente y Admin: Sí, para cualquier cliente o genérica.
    """
    if not getattr(usuario, "is_authenticated", False):
        return False
    if usuario.es_gerente_o_admin:
        return True
    if usuario.es_senior:
        if cliente is None:
            return False
        cid = cliente.pk if hasattr(cliente, "pk") else cliente
        return clientes_visibles_repositorio(usuario).filter(pk=cid).exists()
    return False


def puede_publicar_anonimizado(usuario):
    """Permiso para publicar un ejemplo anonimizado (§7.9): Senior, Gerente y Admin (Junior: 403)."""
    if not getattr(usuario, "is_authenticated", False):
        return False
    return usuario.es_gerente_o_admin or usuario.es_senior


def puede_subir_version_o_restaurar(usuario, documento):
    """Permiso para subir una nueva versión o restaurar una versión anterior como vigente (§7.9)."""
    if not getattr(usuario, "is_authenticated", False):
        return False
    if usuario.es_gerente_o_admin:
        return True
    if not usuario.es_senior:
        return False
    if documento.es_anonimizado:
        return True
    if documento.cliente_id is None:
        return False
    return clientes_visibles_repositorio(usuario).filter(pk=documento.cliente_id).exists()


def puede_dar_de_baja(usuario):
    """Baja lógica de un documento del repositorio: solo Gerente y Admin (§7.9)."""
    if not getattr(usuario, "is_authenticated", False):
        return False
    return usuario.es_gerente_o_admin


def puede_ver_registro_accesos(usuario):
    """El registro de cargas, descargas y restauraciones lo ven solo Gerente y Admin (§7.9, `s2-documento.html`)."""
    if not getattr(usuario, "is_authenticated", False):
        return False
    return usuario.es_gerente_o_admin
