from datetime import date, timedelta
from decimal import Decimal
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from accounts_core.list_utils import parse_post_date
from accounts_core.models import Client, Supplier
from accounts_core.export_names import export_filename
from accounts_core.pdf_utils import render_or_pdf
from auditlog.models import DocumentEventLog
from auditlog.utils import log_audit, log_document_event
from purchases.models import SupplierBill
from treasury.forms import MoneyAccountForm
from treasury.models import MoneyAccount, Payment
from treasury.allocation import clear_payment_allocations
from treasury.payment_flow import post_payment_and_allocate, sync_posted_payment_after_edit
from sales.models import SalesInvoice
from treasury.models import APAllocation, ARAllocation, AccountTransfer, ReconciliationRecord


def _next_temp_receipt_no():
    while True:
        candidate = f"TMP-PAY-{uuid.uuid4().hex[:6].upper()}"
        if not Payment.objects.filter(receipt_no=candidate).exists():
            return candidate


def _validate_payment_party_selection(party_type, client_id, supplier_id, party_name=""):
    if client_id and supplier_id:
        raise ValueError("Choose either client or supplier, not both.")
    if party_type == Payment.PartyType.CLIENT:
        if not client_id:
            raise ValueError("Party type CLIENT requires selecting a client.")
        if supplier_id:
            raise ValueError("Clear supplier when party type is CLIENT.")
    elif party_type == Payment.PartyType.SUPPLIER:
        if not supplier_id:
            raise ValueError("Party type SUPPLIER requires selecting a supplier.")
        if client_id:
            raise ValueError("Clear client when party type is SUPPLIER.")
    elif party_type == Payment.PartyType.OTHER:
        if client_id or supplier_id:
            raise ValueError("Party type OTHER must not have client or supplier selected.")
        if not (party_name or "").strip():
            raise ValueError("Enter a party name for OTHER payments.")


@login_required
def money_accounts_list(request):
    qs = MoneyAccount.objects.order_by("name")
    if request.GET.get("show_inactive") != "1":
        qs = qs.filter(is_active=True)
    return render_or_pdf(
        request,
        "treasury/money_accounts_list.html",
        {"accounts": qs},
        export_filename("Money_Accounts"),
    )


@login_required
def money_account_create(request):
    if request.method == "POST":
        form = MoneyAccountForm(request.POST)
        if form.is_valid():
            account = form.save()
            messages.success(request, f"Money account {account.name} created.")
            return redirect("treasury:money_account_detail", account_id=account.id)
    else:
        form = MoneyAccountForm(initial={"is_active": True, "currency": "USD"})
    return render(
        request,
        "treasury/money_account_form.html",
        {"form": form, "account": None, "is_edit": False},
    )


@login_required
def money_account_edit(request, account_id):
    account = get_object_or_404(MoneyAccount, pk=account_id)
    if request.method == "POST":
        form = MoneyAccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            messages.success(request, f"Money account {account.name} updated.")
            return redirect("treasury:money_account_detail", account_id=account.id)
    else:
        form = MoneyAccountForm(instance=account)
    return render(
        request,
        "treasury/money_account_form.html",
        {"form": form, "account": account, "is_edit": True},
    )


@login_required
def money_account_detail(request, account_id):
    account = get_object_or_404(MoneyAccount, pk=account_id)
    payment_count = account.payments.count()
    return render(
        request,
        "treasury/money_account_detail.html",
        {"account": account, "payment_count": payment_count},
    )


@login_required
@require_http_methods(["POST"])
def money_account_deactivate(request, account_id):
    account = get_object_or_404(MoneyAccount, pk=account_id)
    account.is_active = False
    account.save(update_fields=["is_active"])
    messages.success(request, f"Money account {account.name} deactivated.")
    return redirect("treasury:money_accounts_list")


@login_required
@require_http_methods(["POST"])
def money_account_delete(request, account_id):
    from django.db.models import ProtectedError

    account = get_object_or_404(MoneyAccount, pk=account_id)
    try:
        name = account.name
        account.delete()
        messages.success(request, f"Money account {name} deleted.")
        return redirect("treasury:money_accounts_list")
    except ProtectedError:
        messages.error(request, "Cannot delete: this account has payments. Deactivate instead.")
        return redirect("treasury:money_account_detail", account_id=account_id)


@login_required
def payment_list(request):
    from accounts_core.list_utils import payment_search_filters
    from django.db.models import Prefetch

    qs = (
        Payment.objects.select_related("money_account", "client", "supplier")
        .prefetch_related(
            Prefetch("ar_allocations", queryset=ARAllocation.objects.only("id", "payment_id")),
            Prefetch("ap_allocations", queryset=APAllocation.objects.only("id", "payment_id")),
        )
        .order_by("-created_at")
    )
    qs = payment_search_filters(qs, request)[:500]
    return render_or_pdf(request, "treasury/payment_list.html", {"payments": qs}, export_filename("Payments"))


def _default_payment_date():
    return date.today() - timedelta(days=1)


def _resolve_payment_party_type(direction, party_type):
    if party_type:
        return party_type
    if direction == Payment.Direction.OUT:
        return Payment.PartyType.SUPPLIER
    if direction == Payment.Direction.IN:
        return Payment.PartyType.CLIENT
    return party_type


@login_required
def payment_create(request):
    if request.method == "POST":
        try:
            direction = request.POST.get("direction")
            party_type = _resolve_payment_party_type(direction, request.POST.get("party_type"))
            client_id = request.POST.get("client") or None
            supplier_id = request.POST.get("supplier") or None
            party_name = (request.POST.get("party_name") or "").strip()
            _validate_payment_party_selection(party_type, client_id, supplier_id, party_name)
            pay_date = parse_post_date(request.POST.get("date"), default=_default_payment_date())
            payment = Payment.objects.create(
                receipt_no=request.POST.get("receipt_no") or _next_temp_receipt_no(),
                direction=direction,
                party_type=party_type,
                client_id=client_id if party_type == Payment.PartyType.CLIENT else None,
                supplier_id=supplier_id if party_type == Payment.PartyType.SUPPLIER else None,
                party_name=party_name if party_type == Payment.PartyType.OTHER else "",
                money_account_id=request.POST.get("money_account"),
                payment_method=request.POST.get("payment_method") or "CASH",
                date=pay_date,
                currency=request.POST.get("currency") or "USD",
                amount=Decimal(request.POST.get("amount") or "0"),
                reference=(request.POST.get("reference") or "").strip(),
                note=request.POST.get("note") or "",
                status=Payment.Status.DRAFT,
                is_refund=request.POST.get("is_refund") == "on",
            )
            log_document_event(DocumentEventLog.EventType.CREATED, payment, request.user)
            post_payment_and_allocate(payment, request.user)
            messages.success(
                request,
                f"Payment {payment.receipt_no} saved and posted. "
                f"Unallocated amount remains as client/supplier credit.",
            )
            return redirect("treasury:payment_list")
        except Exception as exc:
            messages.error(request, str(exc))
    return render(
        request,
        "treasury/payment_form.html",
        {
            "is_edit": False,
            "payment": None,
            "default_receipt_no": _next_temp_receipt_no(),
            "default_payment_date": _default_payment_date().isoformat(),
            "accounts": MoneyAccount.objects.filter(is_active=True).order_by("name"),
            "clients": Client.objects.order_by("name_en"),
            "suppliers": Supplier.objects.order_by("name"),
        },
    )


@login_required
def payment_edit(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    if payment.status == Payment.Status.VOIDED:
        messages.error(request, "Voided payments cannot be edited.")
        return redirect("treasury:payment_list")

    if request.method == "POST":
        was_draft = payment.status == Payment.Status.DRAFT
        old_client_id = payment.client_id
        old_supplier_id = payment.supplier_id
        old_direction = payment.direction
        old_party_type = payment.party_type
        try:
            receipt_no = request.POST.get("receipt_no") or payment.receipt_no
            direction = request.POST.get("direction") or payment.direction
            party_type = _resolve_payment_party_type(direction, request.POST.get("party_type") or payment.party_type)
            client_id = request.POST.get("client") or None
            supplier_id = request.POST.get("supplier") or None
            party_name = (request.POST.get("party_name") or "").strip()
            _validate_payment_party_selection(party_type, client_id, supplier_id, party_name)
            money_account_id = request.POST.get("money_account") or payment.money_account_id
            payment_method = request.POST.get("payment_method") or payment.payment_method or "CASH"
            pay_date = parse_post_date(request.POST.get("date"), default=payment.date)
            currency = request.POST.get("currency") or payment.currency
            amount = Decimal(request.POST.get("amount") or "0")
            note = request.POST.get("note") or ""
            is_refund = request.POST.get("is_refund") == "on"

            if amount <= 0:
                raise ValueError("Payment amount must be greater than zero.")

            party_changed = (
                old_client_id != (client_id if party_type == Payment.PartyType.CLIENT else None)
                or old_supplier_id != (supplier_id if party_type == Payment.PartyType.SUPPLIER else None)
                or old_direction != direction
                or old_party_type != party_type
            )

            payment.receipt_no = receipt_no
            payment.direction = direction
            payment.party_type = party_type
            payment.client_id = client_id if party_type == Payment.PartyType.CLIENT else None
            payment.supplier_id = supplier_id if party_type == Payment.PartyType.SUPPLIER else None
            payment.party_name = party_name if party_type == Payment.PartyType.OTHER else ""
            payment.money_account_id = money_account_id
            payment.payment_method = payment_method
            payment.date = pay_date
            payment.currency = currency
            payment.amount = amount
            payment.reference = (request.POST.get("reference") or "").strip()
            payment.note = note
            payment.is_refund = is_refund
            payment.save()

            if was_draft:
                post_payment_and_allocate(payment, request.user)
                messages.success(
                    request,
                    f"Payment {payment.receipt_no} saved and posted. "
                    f"Unallocated amount remains as client/supplier credit.",
                )
            else:
                sync_posted_payment_after_edit(payment, request.user, party_changed=party_changed)
                payment.refresh_from_db()
                messages.success(
                    request,
                    f"Payment {payment.receipt_no} updated. "
                    f"Allocated {payment.allocated_amount} {payment.currency}; "
                    f"{payment.remaining_amount} {payment.currency} unallocated.",
                )
            return redirect("treasury:payment_list")
        except Exception as exc:
            messages.error(request, str(exc))

    return render(
        request,
        "treasury/payment_form.html",
        {
            "is_edit": True,
            "payment": payment,
            "default_receipt_no": payment.receipt_no,
            "accounts": MoneyAccount.objects.filter(is_active=True).order_by("name"),
            "clients": Client.objects.order_by("name_en"),
            "suppliers": Supplier.objects.order_by("name"),
        },
    )


@login_required
def payment_receipt(request, payment_id):
    payment = get_object_or_404(Payment.objects.select_related("client", "supplier", "money_account"), pk=payment_id)
    if payment.client_id:
        party = payment.client.name_en
    elif payment.supplier_id:
        party = payment.supplier.name
    else:
        party = payment.party_name or "Other"
    return render_or_pdf(
        request,
        "treasury/payment_receipt.html",
        {
            "payment": payment,
            "pdf_report_title": "RECEIPT",
            "pdf_report_subtitle": payment.receipt_no,
            "pdf_currency": payment.currency,
        },
        export_filename("Receipt", payment.receipt_no, party),
    )


@login_required
def post_payment(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    try:
        post_payment_and_allocate(payment, request.user)
        messages.success(request, f"Payment {payment.receipt_no} posted and allocated where possible.")
    except Exception as exc:
        messages.error(request, str(exc))
    return redirect("treasury:payment_list")


@login_required
@require_http_methods(["POST"])
def void_payment(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id)
    reason = request.POST.get("reason") or "Manual void"
    try:
        payment.void(reason)
        log_document_event(DocumentEventLog.EventType.VOIDED, payment, request.user, {"reason": reason})
        log_audit("VOID_PAYMENT", payment, actor=request.user, reason=reason)
        messages.success(request, f"Payment {payment.receipt_no} voided.")
    except Exception as exc:
        messages.error(request, str(exc))
    next_url = (request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("treasury:payment_list")


@login_required
@require_http_methods(["POST"])
def payment_delete(request, payment_id):
    from django.db import transaction

    payment = get_object_or_404(Payment, pk=payment_id)
    if payment.status == Payment.Status.VOIDED and (
        payment.ar_allocations.exists() or payment.ap_allocations.exists()
    ):
        messages.error(request, "Cannot delete voided payment with allocations.")
        next_url = (request.POST.get("next") or "").strip()
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("treasury:payment_list")
    if not payment.can_delete():
        messages.error(request, "This payment cannot be deleted.")
        next_url = (request.POST.get("next") or "").strip()
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("treasury:payment_list")
    try:
        with transaction.atomic():
            receipt_no = payment.receipt_no
            if payment.status == Payment.Status.POSTED:
                clear_payment_allocations(payment)
            payment.delete()
        log_audit("DELETE_PAYMENT", payment, actor=request.user, before={"receipt_no": receipt_no})
        messages.success(request, f"Payment {receipt_no} deleted.")
    except ProtectedError:
        messages.error(request, "Cannot delete this payment because it is linked to other records.")
    next_url = (request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect("treasury:payment_list")


@login_required
def ar_allocation_create(request):
    if request.method == "POST":
        payment = get_object_or_404(Payment, pk=request.POST.get("payment"))
        invoice = get_object_or_404(SalesInvoice, pk=request.POST.get("invoice"))
        amount = Decimal(request.POST.get("amount") or "0")

        allocated_total = sum([a.allocated_amount for a in invoice.allocations.all()], Decimal("0.00"))
        invoice_remaining = invoice.grand_total - allocated_total
        payment_remaining = payment.remaining_amount

        if payment.status != Payment.Status.POSTED or invoice.status not in SalesInvoice.reporting_statuses():
            messages.error(request, "Allocation requires posted payment and posted invoice.")
        elif amount <= 0:
            messages.error(request, "Allocation amount must be greater than zero.")
        elif amount > payment_remaining or amount > invoice_remaining:
            messages.error(request, "Allocation exceeds remaining payment or invoice due.")
        else:
            ARAllocation.objects.create(payment=payment, sales_invoice=invoice, allocated_amount=amount)
            log_document_event(DocumentEventLog.EventType.ALLOCATED, invoice, request.user, {"payment": payment.receipt_no, "amount": str(amount)})
            messages.success(request, "Allocation created successfully.")
            return redirect("treasury:ar_allocation_create")

    return render(
        request,
        "treasury/ar_allocation_form.html",
        {
            "payments": Payment.objects.filter(status=Payment.Status.POSTED, direction=Payment.Direction.IN).order_by("-date"),
            "invoices": SalesInvoice.objects.filter(status__in=SalesInvoice.reporting_statuses()).order_by("-issue_date"),
        },
    )


@login_required
def ap_allocation_create(request):
    if request.method == "POST":
        payment = get_object_or_404(Payment, pk=request.POST.get("payment"))
        bill = get_object_or_404(SupplierBill, pk=request.POST.get("bill"))
        amount = Decimal(request.POST.get("amount") or "0")
        try:
            APAllocation.objects.create(payment=payment, supplier_bill=bill, allocated_amount=amount)
            log_document_event(DocumentEventLog.EventType.ALLOCATED, bill, request.user, {"payment": payment.receipt_no, "amount": str(amount)})
            messages.success(request, "AP allocation created successfully.")
            return redirect("treasury:ap_allocation_create")
        except Exception as exc:
            messages.error(request, str(exc))
    return render(
        request,
        "treasury/ap_allocation_form.html",
        {
            "payments": Payment.objects.filter(status=Payment.Status.POSTED, direction=Payment.Direction.OUT).order_by("-date"),
            "bills": SupplierBill.objects.filter(status=SupplierBill.Status.POSTED).order_by("-bill_date"),
        },
    )


@login_required
def reconcile_account(request):
    if request.method == "POST":
        account = get_object_or_404(MoneyAccount, pk=request.POST.get("money_account"))
        rec_date = date.fromisoformat(request.POST.get("reconciliation_date"))
        expected = ReconciliationRecord.compute_expected_balance(account, rec_date)
        physical = Decimal(request.POST.get("physical_count") or "0")
        difference = physical - expected
        reason = request.POST.get("reason") or "Reconciliation"
        record = ReconciliationRecord.objects.create(
            money_account=account,
            reconciliation_date=rec_date,
            expected_closing=expected,
            physical_count=physical,
            difference=difference,
            reason=reason,
        )
        messages.success(request, f"Reconciliation saved. Difference: {record.difference}")
        return redirect("treasury:reconcile_account")
    return render(request, "treasury/reconcile_form.html", {"accounts": MoneyAccount.objects.order_by("name")})


@login_required
def transfer_create(request):
    if request.method == "POST":
        try:
            transfer = AccountTransfer.objects.create(
                from_account_id=request.POST.get("from_account"),
                to_account_id=request.POST.get("to_account"),
                amount=Decimal(request.POST.get("amount") or "0"),
                date=request.POST.get("date"),
                reference=request.POST.get("reference") or "",
            )
            messages.success(request, f"Transfer created: {transfer.id}")
            return redirect("treasury:transfer_create")
        except Exception as exc:
            messages.error(request, str(exc))
    return render(request, "treasury/transfer_form.html", {"accounts": MoneyAccount.objects.filter(is_active=True).order_by("name")})
