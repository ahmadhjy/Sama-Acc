import json
import uuid
from decimal import Decimal

from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from accounts_core.list_utils import invoice_search_filters
from accounts_core.models import get_default_employee_for_accounting
from accounts_core.export_names import export_filename
from accounts_core.pdf_utils import render_or_pdf
from auditlog.models import DocumentEventLog
from auditlog.utils import log_audit, log_document_event
from catalog.models import ServiceType
from sales.forms import SalesInvoiceForm, SalesInvoiceLineFormSet, SalesInvoiceLineSalesFormSet
from sales.models import SalesInvoice, SalesInvoiceAttachment, SalesInvoiceLine


def _save_draft_invoice_with_recalc(form, formset, request=None):
    inv = form.save()
    formset.instance = inv
    formset.save()
    if inv.sales_employee_id:
        inv.lines.filter(line_employee__isnull=True).update(line_employee_id=inv.sales_employee_id)
    inv.refresh_from_db()
    inv.recalc_usd_amounts()
    if request:
        _save_invoice_attachments(request, inv)
    user = request.user if request and request.user.is_authenticated else None
    try:
        inv.publish_changes(user)
        if request:
            log_document_event(DocumentEventLog.EventType.POSTED, inv, user)
    except ValueError as exc:
        if request:
            messages.warning(request, f"Invoice saved as draft: {exc}")
    return inv


def _redirect_after_invoice_save(request, invoice):
    dest = (request.POST.get("leave_after_save") or "").strip()
    if dest and url_has_allowed_host_and_scheme(
        dest,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(dest)
    return redirect("sales:invoice_list")


def _save_invoice_attachments(request, invoice):
    files = request.FILES.getlist("attachments")
    for f in files:
        if f.size > 10 * 1024 * 1024:
            messages.warning(request, f"Skipped {f.name}: file exceeds 10 MB.")
            continue
        SalesInvoiceAttachment.objects.create(
            invoice=invoice,
            file=f,
            original_name=f.name,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )


def _service_field_defs_json():
    types = ServiceType.objects.filter(is_active=True).prefetch_related("field_definitions").order_by("name")
    defs = {}
    for st in types:
        defs[str(st.pk)] = [
            {
                "key": fd.key,
                "label": fd.label,
                "type": fd.field_type,
                "required": fd.required,
                "choices": fd.choices or [],
            }
            for fd in st.field_definitions.all()
        ]
    return json.dumps(defs)


def _next_temp_invoice_no():
    """Display-friendly temporary invoice number before posting assigns final sequence."""
    while True:
        candidate = f"TMP-{uuid.uuid4().hex[:8].upper()}"
        if not SalesInvoice.objects.filter(invoice_no=candidate).exists():
            return candidate


def _invoice_is_persisted(invoice):
    """UUID pk is assigned before save; use _state.adding to detect unsaved invoices."""
    return invoice.pk is not None and not invoice._state.adding


def _invoice_page_context(form, formset, invoice, can_view_cost):
    emp = get_default_employee_for_accounting()
    default_emp = invoice.sales_employee if invoice.sales_employee_id else emp
    if _invoice_is_persisted(invoice):
        line_cost_total = invoice.total_line_cost()
        line_cost_total_usd = invoice.total_line_cost_usd()
        attachments = list(invoice.attachments.all())
    else:
        line_cost_total = Decimal("0.00")
        line_cost_total_usd = Decimal("0.00")
        attachments = []
    return {
        "form": form,
        "formset": formset,
        "invoice": invoice,
        "can_view_cost": can_view_cost,
        "service_field_defs_json": _service_field_defs_json(),
        "default_line_employee_id": str(default_emp.pk) if default_emp else "",
        "initial_line_cost_total": line_cost_total,
        "initial_line_cost_total_usd": line_cost_total_usd,
        "attachments": attachments,
        "invoice_is_new": not _invoice_is_persisted(invoice),
    }


@login_required
def invoice_list(request):
    qs = SalesInvoice.objects.select_related("client", "sales_employee").order_by("-created_at")
    qs = invoice_search_filters(qs, request)[:500]
    return render_or_pdf(request, "sales/invoice_list.html", {"invoices": qs}, export_filename("Invoices"))


@login_required
def invoice_create(request):
    invoice = SalesInvoice()
    can_view_cost = not request.user.groups.filter(name="Sales").exists()
    line_formset_cls = SalesInvoiceLineFormSet if can_view_cost else SalesInvoiceLineSalesFormSet
    if request.method == "POST":
        form = SalesInvoiceForm(request.POST, instance=invoice)
        formset = line_formset_cls(request.POST, instance=invoice)
        if form.is_valid() and formset.is_valid():
            saved_invoice = _save_draft_invoice_with_recalc(form, formset, request)
            log_document_event(DocumentEventLog.EventType.CREATED, saved_invoice, request.user)
            messages.success(request, f"Invoice {saved_invoice.invoice_no} created.")
            return _redirect_after_invoice_save(request, saved_invoice)
    else:
        initial = {"issue_date": timezone.localdate()}
        emp = get_default_employee_for_accounting()
        if emp:
            initial["sales_employee"] = emp
        invoice.invoice_no = _next_temp_invoice_no()
        form = SalesInvoiceForm(instance=invoice, initial=initial)
        formset = line_formset_cls(instance=invoice)
    return render(
        request,
        "sales/invoice_form.html",
        _invoice_page_context(form, formset, invoice, can_view_cost),
    )


@login_required
def invoice_edit(request, invoice_id):
    invoice = get_object_or_404(SalesInvoice, pk=invoice_id)
    can_view_cost = not request.user.groups.filter(name="Sales").exists()
    line_formset_cls = SalesInvoiceLineFormSet if can_view_cost else SalesInvoiceLineSalesFormSet
    if not invoice.is_editable():
        messages.warning(request, "Voided invoices cannot be edited.")
        return redirect("sales:invoice_open", invoice_id=invoice.id)
    if request.method == "POST":
        form = SalesInvoiceForm(request.POST, instance=invoice)
        formset = line_formset_cls(request.POST, instance=invoice)
        if form.is_valid() and formset.is_valid():
            _save_draft_invoice_with_recalc(form, formset, request)
            log_document_event(DocumentEventLog.EventType.UPDATED_DRAFT, invoice, request.user)
            messages.success(request, f"Invoice {invoice.invoice_no} updated.")
            return _redirect_after_invoice_save(request, invoice)
    else:
        form = SalesInvoiceForm(instance=invoice)
        formset = line_formset_cls(instance=invoice)
    return render(
        request,
        "sales/invoice_form.html",
        _invoice_page_context(form, formset, invoice, can_view_cost),
    )


@login_required
def invoice_open(request, invoice_id):
    """Read-only invoice view with void/delete actions."""
    invoice = get_object_or_404(SalesInvoice, pk=invoice_id)
    can_edit = invoice.is_editable()
    can_void = invoice.is_editable() and not invoice.allocations.exists()
    return render(
        request,
        "sales/invoice_detail.html",
        {
            "invoice": invoice,
            "lines": invoice.lines.select_related(
                "service_type", "supplier", "line_employee", "destination"
            ).all(),
            "attachments": invoice.attachments.all(),
            "can_edit": can_edit,
            "can_void": can_void,
            "can_delete": invoice.can_delete()
            and not invoice.allocations.exists()
            and not invoice.credit_notes.exists(),
        },
    )


@login_required
def invoice_pdf(request, invoice_id):
    invoice = get_object_or_404(
        SalesInvoice.objects.select_related("client", "main_destination", "sales_employee"),
        pk=invoice_id,
    )
    version = (request.GET.get("version") or "client").lower()
    show_costs = version == "accountant" and not request.user.groups.filter(name="Sales").exists()
    lines = invoice.lines.select_related("service_type", "supplier", "destination").all()
    pdf_title = "INVOICE"
    if show_costs:
        pdf_title = "INVOICE — Accountant Copy"
    client_name = invoice.client.name_en if invoice.client_id else "Draft"
    subtitle_parts = [invoice.invoice_no, client_name]
    if invoice.main_destination_id:
        subtitle_parts.append(invoice.main_destination.name)
    return render_or_pdf(
        request,
        "sales/invoice_pdf.html",
        {
            "invoice": invoice,
            "lines": lines,
            "show_costs": show_costs,
            "pdf_report_title": pdf_title,
            "pdf_report_subtitle": " — ".join(subtitle_parts),
            "pdf_currency": invoice.currency,
            "pdf_account_range": f"Client: {client_name}",
        },
        export_filename(
            "Invoice",
            invoice.invoice_no,
            client_name,
            "accountant" if show_costs else "client",
        ),
    )


@login_required
@require_http_methods(["POST"])
def invoice_delete_attachment(request, invoice_id, attachment_id):
    invoice = get_object_or_404(SalesInvoice, pk=invoice_id)
    if not invoice.is_editable():
        messages.error(request, "Attachments cannot be removed from voided invoices.")
        return redirect("sales:invoice_open", invoice_id=invoice.id)
    att = get_object_or_404(SalesInvoiceAttachment, pk=attachment_id, invoice=invoice)
    att.file.delete(save=False)
    att.delete()
    messages.success(request, "Attachment removed.")
    return redirect("sales:invoice_edit", invoice_id=invoice.id)


@login_required
@require_http_methods(["POST"])
def invoice_delete(request, invoice_id):
    invoice = get_object_or_404(SalesInvoice, pk=invoice_id)
    if not invoice.can_delete():
        messages.error(request, "Only draft or voided invoices can be deleted.")
        return redirect("sales:invoice_list")
    if invoice.allocations.exists():
        messages.error(request, "Cannot delete invoice with payment allocations.")
        return redirect("sales:invoice_open", invoice_id=invoice.id)
    if invoice.credit_notes.exists():
        messages.error(request, "Cannot delete invoice with linked credit notes.")
        return redirect("sales:invoice_open", invoice_id=invoice.id)
    try:
        invoice_no = invoice.invoice_no
        invoice.delete()
        log_audit("DELETE_INVOICE", invoice, actor=request.user, before={"invoice_no": invoice_no})
        messages.success(request, f"Invoice {invoice_no} deleted.")
    except ProtectedError:
        messages.error(request, "Cannot delete this invoice because it is linked to other records.")
        return redirect("sales:invoice_open", invoice_id=invoice.id)
    return redirect("sales:invoice_list")


@login_required
def post_invoice(request, invoice_id):
    """Posting is automatic on save; keep URL for old bookmarks."""
    messages.info(request, "Invoices are saved and updated automatically. Use Edit to change this invoice.")
    return redirect("sales:invoice_edit", invoice_id=invoice_id)


@login_required
@require_http_methods(["POST"])
def void_invoice(request, invoice_id):
    invoice = get_object_or_404(SalesInvoice, pk=invoice_id)
    reason = request.POST.get("reason") or "Manual void"
    try:
        invoice.void(request.user, reason)
        log_document_event(DocumentEventLog.EventType.VOIDED, invoice, request.user, {"reason": reason})
        log_audit("VOID_INVOICE", invoice, actor=request.user, reason=reason)
        messages.success(request, f"Invoice {invoice.invoice_no} voided.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("sales:invoice_list")


@login_required
def adjust_invoice(request, invoice_id):
    invoice = get_object_or_404(SalesInvoice, pk=invoice_id)
    if invoice.status != SalesInvoice.Status.POSTED:
        messages.error(request, "Only posted invoices can be adjusted.")
        return redirect("sales:invoice_list")
    if not (request.user.is_superuser or request.user.groups.filter(name__in=["Accounting", "Admin"]).exists()):
        messages.error(request, "Only Accounting/Admin can adjust posted invoices.")
        return redirect("sales:invoice_list")
    if invoice.allocations.exists():
        messages.error(request, "Cannot adjust invoice with existing allocations. De-allocate first.")
        return redirect("sales:invoice_list")

    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "Adjustment reason is required.")
            return render(request, "sales/invoice_adjust_form.html", {"invoice": invoice})
        with transaction.atomic():
            old_invoice_no = invoice.invoice_no
            old_invoice_id = invoice.id
            corrected = SalesInvoice.objects.create(
                invoice_no=_next_temp_invoice_no(),
                client=invoice.client,
                file=invoice.file,
                sales_employee=invoice.sales_employee,
                package_type=invoice.package_type,
                issue_date=invoice.issue_date,
                due_date=invoice.due_date,
                currency=invoice.currency,
                exchange_rate_to_usd=invoice.exchange_rate_to_usd,
                grand_total=invoice.grand_total,
                grand_total_usd=Decimal("0.00"),
                subtotal_usd=Decimal("0.00"),
                discount_total_usd=Decimal("0.00"),
                status=SalesInvoice.Status.DRAFT,
            )
            SalesInvoiceLine.objects.bulk_create(
                [
                    SalesInvoiceLine(
                        invoice=corrected,
                        service_type=line.service_type,
                        line_data=line.line_data or {},
                        line_employee=line.line_employee,
                        supplier=line.supplier,
                        service_instance=line.service_instance,
                        qty=line.qty,
                        sell_price=line.sell_price,
                        cost_price=line.cost_price,
                        line_discount=line.line_discount,
                        sell_price_usd=line.sell_price_usd,
                        cost_price_usd=line.cost_price_usd,
                        line_discount_usd=line.line_discount_usd,
                        service_date=line.service_date,
                        destination=line.destination,
                        notes=line.notes,
                        sort_order=line.sort_order,
                    )
                    for line in invoice.lines.all()
                ]
            )
            corrected.refresh_from_db()
            corrected.recalc_totals_from_lines()
            corrected.recalc_usd_amounts()
            invoice.void(request.user, f"Adjusted to {corrected.invoice_no}. Reason: {reason}")
            log_document_event(
                DocumentEventLog.EventType.VOIDED,
                invoice,
                request.user,
                {"reason": reason, "adjusted_to": corrected.invoice_no},
            )
            invoice.delete()
            log_document_event(
                DocumentEventLog.EventType.CREATED,
                corrected,
                request.user,
                {"adjusted_from": old_invoice_no, "reason": reason},
            )
            log_audit(
                "ADJUST_INVOICE",
                corrected,
                actor=request.user,
                reason=reason,
                before={"invoice_no": old_invoice_no, "invoice_id": str(old_invoice_id)},
                after={"invoice_no": corrected.invoice_no},
            )
        messages.success(
            request,
            f"Invoice {old_invoice_no} adjusted. Correction draft {corrected.invoice_no} created.",
        )
        return redirect("sales:invoice_edit", invoice_id=corrected.id)

    return render(request, "sales/invoice_adjust_form.html", {"invoice": invoice})
