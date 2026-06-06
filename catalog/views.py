from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import ProtectedError, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts_core.list_utils import service_instance_list_filters, service_type_list_filters
from accounts_core.pdf_utils import render_or_pdf
from catalog.forms import ServiceFieldInlineFormSet, ServiceTypeForm
from catalog.models import Destination, ServiceInstance, ServiceType


def destination_search(request):
    q = (request.GET.get("q") or "").strip()
    qs = Destination.objects.filter(is_active=True).order_by("sort_order", "name")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(country__icontains=q))[:30]
    else:
        qs = qs[:100]
    return JsonResponse(
        [{"id": str(d.id), "name": d.name, "country": d.country} for d in qs],
        safe=False,
    )


@login_required
@require_http_methods(["POST"])
def destination_quick_create(request):
    import json

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    name = (payload.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "Destination name is required."}, status=400)

    country = (payload.get("country") or "").strip()
    if Destination.objects.filter(name__iexact=name).exists():
        dest = Destination.objects.get(name__iexact=name)
        return JsonResponse({"id": str(dest.id), "name": dest.name, "country": dest.country})

    dest = Destination.objects.create(name=name, country=country, is_active=True)
    return JsonResponse({"id": str(dest.id), "name": dest.name, "country": dest.country})

@login_required
def service_types_list(request):
    qs = ServiceType.objects.prefetch_related("field_definitions").order_by("name")
    if request.GET.get("show_inactive") != "1":
        qs = qs.filter(is_active=True)
    service_types = service_type_list_filters(qs, request)
    return render_or_pdf(
        request,
        "catalog/service_types_list.html",
        {"service_types": service_types},
        "service_types.pdf",
    )


@login_required
def service_type_create(request):
    service_type = ServiceType()
    if request.method == "POST":
        form = ServiceTypeForm(request.POST, instance=service_type)
        formset = ServiceFieldInlineFormSet(request.POST, instance=service_type)
        if form.is_valid() and formset.is_valid():
            st = form.save()
            formset.instance = st
            formset.save()
            messages.success(request, f"Service type {st.name} created.")
            return redirect("catalog:service_type_edit", service_type_id=st.id)
    else:
        form = ServiceTypeForm(instance=service_type)
        formset = ServiceFieldInlineFormSet(instance=service_type)
    return render(
        request,
        "catalog/service_type_form.html",
        {"form": form, "formset": formset, "service_type": None, "is_edit": False},
    )


@login_required
def service_type_edit(request, service_type_id):
    service_type = get_object_or_404(ServiceType, pk=service_type_id)
    if request.method == "POST":
        form = ServiceTypeForm(request.POST, instance=service_type)
        formset = ServiceFieldInlineFormSet(request.POST, instance=service_type)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f"Service type {service_type.name} updated.")
            return redirect("catalog:service_type_detail", service_type_id=service_type.id)
    else:
        form = ServiceTypeForm(instance=service_type)
        formset = ServiceFieldInlineFormSet(instance=service_type)
    return render(
        request,
        "catalog/service_type_form.html",
        {"form": form, "formset": formset, "service_type": service_type, "is_edit": True},
    )


@login_required
def service_type_detail(request, service_type_id):
    service_type = get_object_or_404(
        ServiceType.objects.prefetch_related("field_definitions"),
        pk=service_type_id,
    )
    return render(request, "catalog/service_type_detail.html", {"service_type": service_type})


@login_required
@require_http_methods(["POST"])
def service_type_deactivate(request, service_type_id):
    service_type = get_object_or_404(ServiceType, pk=service_type_id)
    service_type.is_active = False
    service_type.save(update_fields=["is_active"])
    messages.success(request, f"Service type {service_type.name} deactivated.")
    return redirect("catalog:service_types_list")


@login_required
@require_http_methods(["POST"])
def service_type_delete(request, service_type_id):
    service_type = get_object_or_404(ServiceType, pk=service_type_id)
    try:
        name = service_type.name
        service_type.delete()
        messages.success(request, f"Service type {name} deleted.")
        return redirect("catalog:service_types_list")
    except ProtectedError:
        messages.error(request, "Cannot delete: this service type is in use. Deactivate instead.")
        return redirect("catalog:service_type_detail", service_type_id=service_type_id)


def service_instances_list(request):
    qs = ServiceInstance.objects.select_related("service_type", "passenger", "supplier").order_by("-created_at")
    service_instances = service_instance_list_filters(qs, request)[:500]
    return render_or_pdf(
        request,
        "catalog/service_instances_list.html",
        {"service_instances": service_instances},
        "service_instances.pdf",
    )
