from django.contrib.auth.decorators import login_required
from django.urls import path

from . import views

app_name = "accounts_core"

urlpatterns = [
    path("", login_required(views.dashboard), name="dashboard"),
    path("login/", views.AppLoginView.as_view(), name="login"),
    path("clients/", views.clients_list, name="clients_list"),
    path("clients/new/", views.client_create, name="client_create"),
    path("clients/<uuid:client_id>/edit/", views.client_edit, name="client_edit"),
    path("clients/quick-create/", views.client_quick_create, name="client_quick_create"),
    path("suppliers/", views.suppliers_list, name="suppliers_list"),
    path("suppliers/new/", views.supplier_create, name="supplier_create"),
    path("suppliers/quick-create/", views.supplier_quick_create, name="supplier_quick_create"),
    path("suppliers/<uuid:supplier_id>/", views.supplier_detail, name="supplier_detail"),
    path("suppliers/<uuid:supplier_id>/edit/", views.supplier_edit, name="supplier_edit"),
    path("suppliers/<uuid:supplier_id>/deactivate/", views.supplier_deactivate, name="supplier_deactivate"),
    path("suppliers/<uuid:supplier_id>/delete/", views.supplier_delete, name="supplier_delete"),
]
