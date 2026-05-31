from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from accounts_core.forms import ClientForm, SupplierForm
from accounts_core.list_utils import client_list_filters, supplier_list_filters
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
    from reporting.report_summary import build_report_summary

    date_from, date_to, period_label = resolve_report_dates(request)
    hub_tab = (request.GET.get("tab") or "overview").lower()
    if hub_tab not in ("overview", "reports"):
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
        **build_dashboard_analytics(request),
        **build_report_summary(request),
    }
    return render(request, "dashboard.html", context)


def _next_client_code():
    """Suggest next client code C-0001, C-0002, …"""
    max_n = 0
    for code in Client.objects.values_list("client_code", flat=True):
        if code.startswith("C-") and len(code) > 2 and code[2:].isdigit():
            max_n = max(max_n, int(code[2:]))
    return f"C-{max_n + 1:04d}"


@login_required
def clients_list(request):
    qs = Client.objects.order_by("name_en")
    clients = client_list_filters(qs, request)[:500]
    return render_or_pdf(request, "accounts_core/clients_list.html", {"clients": clients}, "clients.pdf")


@login_required
def client_create(request):
    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            messages.success(request, f"Client {client.name_en} created.")
            return redirect("accounts_core:client_edit", client_id=client.id)
    else:
        form = ClientForm(initial={"client_code": _next_client_code()})
    return render(request, "accounts_core/client_form.html", {"form": form, "client": None, "is_edit": False})


@login_required
def client_edit(request, client_id):
    client = get_object_or_404(Client, pk=client_id)
    if request.method == "POST":
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, f"Client {client.name_en} updated.")
            return redirect("accounts_core:client_edit", client_id=client.id)
    else:
        form = ClientForm(instance=client)
    return render(request, "accounts_core/client_form.html", {"form": form, "client": client, "is_edit": True})


def _next_supplier_code():
    max_n = 0
    for code in Supplier.objects.values_list("supplier_code", flat=True):
        if code.startswith("S-") and len(code) > 2 and code[2:].isdigit():
            max_n = max(max_n, int(code[2:]))
    return f"S-{max_n + 1:04d}"


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
        "suppliers.pdf",
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
        form = SupplierForm(initial={"supplier_code": _next_supplier_code(), "is_active": True})
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
