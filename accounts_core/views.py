from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts_core.employee_forms import EmployeeForm
from accounts_core.forms import ClientForm, SupplierForm
from accounts_core.list_utils import client_list_filters, supplier_list_filters
from auditlog.utils import log_audit
from accounts_core.party_codes import next_client_code, next_supplier_code
from accounts_core.export_names import export_filename
from accounts_core.models import BookingFile, Client, Employee, Supplier
from accounts_core.pdf_utils import render_or_pdf
from purchases.models import SupplierBill
from sales.models import SalesInvoice
from treasury.models import Payment


class AppLoginView(LoginView):
    template_name = "accounts_core/login.html"
    redirect_authenticated_user = True


def dashboard(request):
    from reporting.analytics import build_dashboard_analytics
    from reporting.date_ranges import resolve_report_dates
    from reporting.invoice_pl import period_cogs_usd, period_opex_usd, period_revenue_usd
    from reporting.report_summary import build_report_summary

    date_from, date_to, period_label = resolve_report_dates(request)
    hub_tab = (request.GET.get("tab") or "overview").lower()
    if hub_tab not in ("overview", "reports", "destinations"):
        hub_tab = "overview"

    context = {
        "hub_tab": hub_tab,
        "date_from": date_from,
        "date_to": date_to,
        "period_label": period_label,
        "client_count": Client.objects.count(),
        "supplier_count": Supplier.objects.count(),
        "invoice_count": SalesInvoice.objects.count(),
        "bill_count": SupplierBill.objects.count(),
        "payment_count": Payment.objects.count(),
        "file_count": BookingFile.objects.count(),
        "employee_count": Employee.objects.count(),
        "latest_invoices": SalesInvoice.objects.select_related("client").order_by("-created_at")[:10],
        "latest_payments": Payment.objects.select_related("money_account").order_by("-created_at")[:10],
    }

    # Compute period P&L once and share across overview/reports (was double-scanned).
    revenue = cogs = opex = None
    if hub_tab in ("overview", "reports"):
        revenue = period_revenue_usd(date_from, date_to)
        cogs = period_cogs_usd(date_from, date_to)
        opex = period_opex_usd(date_from, date_to)

    if hub_tab == "overview":
        context.update(
            build_dashboard_analytics(
                request,
                revenue=revenue,
                cogs=cogs,
                opex_total=opex,
            )
        )
    elif hub_tab == "reports":
        context.update(
            build_report_summary(
                request,
                revenue=revenue,
                cogs=cogs,
                opex_total=opex,
            )
        )
    else:
        from reporting.destination_stats import build_destination_stats

        context.update(build_destination_stats(date_from, date_to))

    return render(request, "dashboard.html", context)


@login_required
def clients_list(request):
    qs = Client.objects.order_by("name_en")
    clients = client_list_filters(qs, request)[:500]
    return render_or_pdf(request, "accounts_core/clients_list.html", {"clients": clients}, export_filename("Clients"))


@login_required
def client_create(request):
    if request.method == "POST":
        form = ClientForm(request.POST, request.FILES)
        if form.is_valid():
            client = form.save()
            messages.success(request, f"Client {client.name_en} created.")
            return redirect("accounts_core:client_edit", client_id=client.id)
    else:
        form = ClientForm(initial={"client_code": next_client_code()})
    return render(request, "accounts_core/client_form.html", {"form": form, "client": None, "is_edit": False})


@login_required
def client_edit(request, client_id):
    client = get_object_or_404(Client, pk=client_id)
    if request.method == "POST":
        form = ClientForm(request.POST, request.FILES, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, f"Client {client.name_en} updated.")
            return redirect("accounts_core:client_edit", client_id=client.id)
    else:
        form = ClientForm(instance=client)
    return render(request, "accounts_core/client_form.html", {"form": form, "client": client, "is_edit": True})


@login_required
def suppliers_list(request):
    from datetime import date
    from decimal import Decimal

    from accounts_core.list_utils import parse_date
    from reporting.balances import supplier_ap_balance

    qs = Supplier.objects.order_by("name")
    qs = supplier_list_filters(qs, request)
    today = date.today()
    min_balance = request.GET.get("min_balance")
    sort_by = request.GET.get("sort", "name")
    rows = []
    for supplier in qs:
        balance = supplier_ap_balance(supplier, today)
        rows.append({"supplier": supplier, "balance": balance})
    if min_balance:
        try:
            mb = Decimal(min_balance)
            rows = [r for r in rows if r["balance"] >= mb]
        except Exception:
            pass
    if sort_by == "balance":
        rows.sort(key=lambda r: r["balance"], reverse=True)
    else:
        rows.sort(key=lambda r: r["supplier"].name.lower())
    return render_or_pdf(
        request,
        "accounts_core/suppliers_list.html",
        {"supplier_rows": rows[:500], "min_balance": min_balance or "", "sort": sort_by},
        export_filename("Suppliers"),
    )


@login_required
def supplier_create(request):
    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save()
            messages.success(request, f"Supplier {supplier.name} created.")
            return redirect("accounts_core:supplier_edit", supplier_id=supplier.id)
    else:
        form = SupplierForm(initial={"supplier_code": next_supplier_code(), "is_active": True})
    return render(
        request,
        "accounts_core/supplier_form.html",
        {"form": form, "supplier": None, "is_edit": False},
    )


@login_required
def supplier_edit(request, supplier_id):
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, f"Supplier {supplier.name} updated.")
            return redirect("accounts_core:supplier_detail", supplier_id=supplier.id)
    else:
        form = SupplierForm(instance=supplier)
    return render(
        request,
        "accounts_core/supplier_form.html",
        {"form": form, "supplier": supplier, "is_edit": True},
    )


@login_required
def supplier_detail(request, supplier_id):
    from datetime import date
    from reporting.balances import supplier_ap_balance

    supplier = get_object_or_404(Supplier, pk=supplier_id)
    return render(
        request,
        "accounts_core/supplier_detail.html",
        {
            "supplier": supplier,
            "balance": supplier_ap_balance(supplier, date.today()),
        },
    )


@login_required
@require_http_methods(["POST"])
def supplier_deactivate(request, supplier_id):
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    supplier.is_active = False
    supplier.save(update_fields=["is_active"])
    messages.success(request, f"Supplier {supplier.name} deactivated.")
    return redirect("accounts_core:suppliers_list")


@login_required
@require_http_methods(["POST"])
def supplier_delete(request, supplier_id):
    supplier = get_object_or_404(Supplier, pk=supplier_id)
    try:
        name = supplier.name
        supplier.delete()
        messages.success(request, f"Supplier {name} deleted.")
        return redirect("accounts_core:suppliers_list")
    except ProtectedError:
        messages.error(request, "Cannot delete: this supplier is used on invoices, bills, or other records. Deactivate instead.")
        return redirect("accounts_core:supplier_detail", supplier_id=supplier_id)


@login_required
@require_http_methods(["POST"])
def client_quick_create(request):
    """Minimal client create from invoice form (JSON)."""
    import json

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    name_en = (payload.get("name_en") or "").strip()
    if not name_en:
        return JsonResponse({"error": "Client name is required."}, status=400)
    phone = (payload.get("phone") or "").strip()
    if not phone:
        return JsonResponse({"error": "Phone number is required."}, status=400)

    client_type = (payload.get("type") or Client.ClientType.INDIVIDUAL)
    if client_type == Client.ClientType.CORPORATE:
        contact = (payload.get("contact_person") or "").strip()
        if not contact:
            return JsonResponse({"error": "Contact person is required for corporate clients."}, status=400)

    client_code = (payload.get("client_code") or "").strip() or next_client_code()
    if Client.objects.filter(client_code=client_code).exists():
        return JsonResponse({"error": f"Client code {client_code} already exists."}, status=400)

    client = Client.objects.create(
        client_code=client_code,
        name_en=name_en,
        phone=phone,
        type=client_type,
        email=(payload.get("email") or "").strip(),
        address=(payload.get("address") or "").strip(),
        contact_person=(payload.get("contact_person") or "").strip(),
    )
    if payload.get("date_of_birth"):
        from accounts_core.list_utils import parse_post_date

        try:
            client.date_of_birth = parse_post_date(payload.get("date_of_birth"))
            client.save(update_fields=["date_of_birth"])
        except ValueError:
            pass
    return JsonResponse({"id": str(client.id), "name": client.name_en, "client_code": client.client_code})


@login_required
@require_http_methods(["POST"])
def supplier_quick_create(request):
    """Minimal supplier create from invoice service line (JSON)."""
    import json

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    name = (payload.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "Supplier name is required."}, status=400)

    managing = (payload.get("managing_number") or "").strip()
    accounting = (payload.get("accounting_number") or "").strip()
    if not managing and not accounting:
        return JsonResponse({"error": "Enter at least one of managing number or accounting number."}, status=400)

    supplier_code = (payload.get("supplier_code") or "").strip() or next_supplier_code()
    if Supplier.objects.filter(supplier_code=supplier_code).exists():
        return JsonResponse({"error": f"Supplier code {supplier_code} already exists."}, status=400)

    supplier = Supplier.objects.create(
        supplier_code=supplier_code,
        name=name,
        managing_number=managing,
        accounting_number=accounting,
        phones=[n for n in (managing, accounting) if n],
        type=(payload.get("type") or Supplier.SupplierType.OTHER),
        email=(payload.get("email") or "").strip(),
        address=(payload.get("address") or "").strip(),
        default_currency=(payload.get("default_currency") or "USD").strip()[:3] or "USD",
        is_active=True,
    )
    return JsonResponse({"id": str(supplier.id), "name": supplier.name, "supplier_code": supplier.supplier_code})


@login_required
def employees_list(request):
    q = (request.GET.get("q") or "").strip()
    qs = Employee.objects.order_by("name")
    if q:
        from django.db.models import Q

        qs = qs.filter(
            Q(name__icontains=q)
            | Q(first_name__icontains=q)
            | Q(father_name__icontains=q)
            | Q(last_name__icontains=q)
        )
    return render_or_pdf(
        request,
        "accounts_core/employees_list.html",
        {"employees": qs[:500], "q": q},
        export_filename("Employees"),
    )


@login_required
def employee_create(request):
    if request.method == "POST":
        form = EmployeeForm(request.POST, request.FILES)
        if form.is_valid():
            employee = form.save()
            messages.success(request, f"Employee {employee.name} created.")
            return redirect("accounts_core:employee_edit", employee_id=employee.id)
    else:
        form = EmployeeForm()
    return render(
        request,
        "accounts_core/employee_form.html",
        {"form": form, "employee": None, "is_edit": False},
    )


@login_required
def employee_edit(request, employee_id):
    employee = get_object_or_404(Employee, pk=employee_id)
    if request.method == "POST":
        form = EmployeeForm(request.POST, request.FILES, instance=employee)
        if form.is_valid():
            form.save()
            messages.success(request, f"Employee {employee.name} updated.")
            return redirect("accounts_core:employee_edit", employee_id=employee.id)
    else:
        form = EmployeeForm(instance=employee)
    return render(
        request,
        "accounts_core/employee_form.html",
        {
            "form": form,
            "employee": employee,
            "is_edit": True,
        },
    )
