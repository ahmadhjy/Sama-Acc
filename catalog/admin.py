from django.contrib import admin

from catalog.models import Destination, ServiceFieldDefinition, ServiceInstance, ServiceType


@admin.register(Destination)
class DestinationAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "is_active", "sort_order")
    search_fields = ("name", "country")
    list_filter = ("is_active",)


class ServiceFieldDefinitionInline(admin.TabularInline):
    model = ServiceFieldDefinition
    extra = 0
    ordering = ("order", "key")


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "requires_supplier")
    search_fields = ("code", "name")
    list_filter = ("is_active", "requires_supplier")
    inlines = [ServiceFieldDefinitionInline]


@admin.register(ServiceInstance)
class ServiceInstanceAdmin(admin.ModelAdmin):
    search_fields = ("service_type__name", "service_type__code", "notes")
    list_display = ("service_type", "created_at")
    autocomplete_fields = ("service_type", "passenger", "supplier")


@admin.register(ServiceFieldDefinition)
class ServiceFieldDefinitionAdmin(admin.ModelAdmin):
    list_display = ("service_type", "key", "label", "field_type", "required", "order")
    search_fields = ("key", "label", "service_type__code", "service_type__name")
    list_filter = ("field_type", "required")
    autocomplete_fields = ("service_type",)
    ordering = ("service_type", "order", "key")
