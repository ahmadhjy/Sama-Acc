from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("destinations/search/", views.destination_search, name="destination_search"),
    path("destinations/quick-create/", views.destination_quick_create, name="destination_quick_create"),
    path("service-types/", views.service_types_list, name="service_types_list"),
    path("service-types/new/", views.service_type_create, name="service_type_create"),
    path("service-types/<uuid:service_type_id>/", views.service_type_detail, name="service_type_detail"),
    path("service-types/<uuid:service_type_id>/edit/", views.service_type_edit, name="service_type_edit"),
    path("service-types/<uuid:service_type_id>/deactivate/", views.service_type_deactivate, name="service_type_deactivate"),
    path("service-types/<uuid:service_type_id>/delete/", views.service_type_delete, name="service_type_delete"),
    path("service-instances/", views.service_instances_list, name="service_instances_list"),
]
