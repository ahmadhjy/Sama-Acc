from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from accounts_core.list_utils import bill_search_filters
from accounts_core.export_names import export_filename
from accounts_core.pdf_utils import render_or_pdf
from auditlog.models import DocumentEventLog
from auditlog.utils import log_audit, log_document_event
from purchases.forms import SupplierBillForm, SupplierBillLineFormSet
from purchases.models import SupplierBill


@login_required
def bill_list(request):
    qs = SupplierBill.objects.select_related("supplier").order_by("-created_at")
    bills = bill_search_filters(qs, request)[:500]
    return render_or_pdf(request, "purchases/bill_list.html", {"bills": bills}, export_filename("Supplier_Bills"))


@login_required
def bill_create(request):
    bill = SupplierBill()
    if request.method == "POST":
        form = SupplierBillForm(request.POST, instance=bill)
        formset = SupplierBillLineFormSet(request.POST, instance=bill)
        if form.is_valid() and formset.is_valid():
            saved_bill = form.save()
            formset.instance = saved_bill
            formset.save()
            log_document_event(DocumentEventLog.EventType.CREATED, saved_bill, request.user)
            messages.success(request, f"Bill {saved_bill.bill_no} created.")
            return redirect("purchases:bill_edit", bill_id=saved_bill.id)
    else:
        form = SupplierBillForm(instance=bill)
        formset = SupplierBillLineFormSet(instance=bill)
    return render(request, "purchases/bill_form.html", {"form": form, "formset": formset, "bill": bill})


@login_required
def bill_open(request, bill_id):
    bill = get_object_or_404(
        SupplierBill.objects.select_related("supplier").prefetch_related(
            "lines__sales_invoice_line__invoice"
        ),
        pk=bill_id,
    )
    return render(
        request,
        "purchases/bill_detail.html",
        {"bill": bill, "lines": bill.lines.all()},
    )


@login_required
def bill_edit(request, bill_id):
    bill = get_object_or_404(SupplierBill, pk=bill_id)
    if bill.status != SupplierBill.Status.DRAFT:
        messages.warning(request, "Only draft bills can be edited.")
        return redirect("purchases:bill_list")
    if request.method == "POST":
        form = SupplierBillForm(request.POST, instance=bill)
        formset = SupplierBillLineFormSet(request.POST, instance=bill)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            log_document_event(DocumentEventLog.EventType.UPDATED_DRAFT, bill, request.user)
            messages.success(request, f"Bill {bill.bill_no} updated.")
            return redirect("purchases:bill_edit", bill_id=bill.id)
    else:
        form = SupplierBillForm(instance=bill)
        formset = SupplierBillLineFormSet(instance=bill)
    return render(request, "purchases/bill_form.html", {"form": form, "formset": formset, "bill": bill})


@login_required
def post_bill(request, bill_id):
    bill = get_object_or_404(SupplierBill, pk=bill_id)
    try:
        bill.post(request.user if request.user.is_authenticated else None)
        log_document_event(DocumentEventLog.EventType.POSTED, bill, request.user)
        log_audit("POST_BILL", bill, actor=request.user)
        messages.success(request, f"Bill {bill.bill_no} posted successfully.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("purchases:bill_list")


@login_required
@require_http_methods(["POST"])
def void_bill(request, bill_id):
    bill = get_object_or_404(SupplierBill, pk=bill_id)
    if bill.status != SupplierBill.Status.POSTED:
        messages.error(request, "Only posted bills can be voided.")
        return redirect("purchases:bill_list")
    bill.status = SupplierBill.Status.VOIDED
    bill.save(update_fields=["status"])
    log_document_event(DocumentEventLog.EventType.VOIDED, bill, request.user)
    log_audit("VOID_BILL", bill, actor=request.user)
    messages.success(request, f"Bill {bill.bill_no} voided.")
    return redirect("purchases:bill_list")
