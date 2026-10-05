from django.urls import path, re_path

from . import views

# /clientes/, /contratos/ y /plantillas/ (SDD §14): listado, alta y edición. `gestion/` es el acceso común.
_ENTIDADES = r"(?P<entidad>clientes|contratos|plantillas)"

urlpatterns = [
    path("gestion/", views.gestion, name="gestion"),
    re_path(rf"^{_ENTIDADES}/$", views.lista, name="adm_lista"),
    re_path(rf"^{_ENTIDADES}/nuevo/$", views.editar, name="adm_nuevo"),
    re_path(rf"^{_ENTIDADES}/(?P<pk>[0-9]+)/$", views.editar, name="adm_editar"),
]
