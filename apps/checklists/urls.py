from django.urls import path

from . import views

urlpatterns = [
    # Checklist por TDR (RF-44)
    path("entregables/<int:pk>/checklist/", views.checklist_tdr, name="entregable_checklist"),
    path("checklists/", views.checklists, name="checklists"),
    # Checklist de control de calidad (RF-45)
    path("entregables/<int:pk>/calidad/", views.revision_calidad, name="entregable_calidad"),
    path("calidad/", views.calidad, name="calidad"),
]
