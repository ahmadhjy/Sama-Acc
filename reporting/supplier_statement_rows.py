from datetime import date
from decimal import Decimal

from purchases.models import SupplierLedgerLine
from reporting.statement_refs import invoice_ref_url
from reporting.statement_sort import sort_statement_rows
from sales.models import SalesInvoice, SalesInvoiceLine
from treasury.models import Payment

# Migrated SATO26 docs keep ledger as source of truth; live ERP docs use INV-/PAY- prefixes.
LEGACY_DOC_PREFIX = "SATO26-"


def _supplier_payments_qs(supplier, date_from=None, date_to=None, direction=None):
    qs = Payment.objects.filter(
        supplier=supplier,
        party_type=Payment.PartyType.SUPPLIER,
        status=Payment.Status.POSTED,
    ).select_related("money_account")
    if direction:
        qs = qs.filter(direction=direction)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    return qs


def _live_supplier_payments_qs(supplier, date_from=None, date_to=None, direction=None, on_or_before=None):
    """Posted supplier payments created in the live ERP (not migrated SATO26 receipts)."""
    qs = _supplier_payments_qs(supplier, date_from, date_to, direction).exclude(
        receipt_no__startswith=LEGACY_DOC_PREFIX
    )
    if on_or_before is not None:
        qs = qs.filter(date__lte=on_or_before)
    return qs


def _payment_supplier_description(payment: Payment) -> str:
    return payment.money_account.name if payment.money_account_id else "—"


def _line_visible_by_report_dates(line, date_from=None, date_to=None):
    line_date = line.effective_service_date()
    if date_from and line_date and line_date < date_from:
        return False
    if date_to and line_date and line_date > date_to:
        return False
    return True


def _supplier_ledger_qs(supplier, date_from=None, date_to=None, on_or_before=None):
    qs = SupplierLedgerLine.objects.filter(supplier=supplier)
    if on_or_before is not None:
        qs = qs.filter(line_date__lte=on_or_before)
    if date_from:
        qs = qs.filter(line_date__gte=date_from)
    if date_to:
        qs = qs.filter(line_date__lte=date_to)
    return qs.order_by("line_date", "journal_type", "legacy_jvno", "line_seq")


def _invoice_id_for_no(invoice_no: str):
    if not invoice_no:
        return None
    inv = SalesInvoice.objects.filter(invoice_no=invoice_no).only("id").first()
    return inv.id if inv else None


def _ledger_row_type(line: SupplierLedgerLine) -> str:
    if line.journal_type == "SI" and line.dc == SupplierLedgerLine.DC.CREDIT:
        return "Purchase"
    if line.journal_type in ("PV", "RV") and line.dc == SupplierLedgerLine.DC.DEBIT:
        return "Payment"
    if line.journal_type in ("PV", "RV") and line.dc == SupplierLedgerLine.DC.CREDIT:
        return "Receipt"
    return f"{line.journal_type} {'Credit' if line.dc == SupplierLedgerLine.DC.CREDIT else 'Debit'}"


def supplier_has_ledger(supplier) -> bool:
    return SupplierLedgerLine.objects.filter(supplier=supplier).exists()


def _live_supplier_invoice_lines_qs(supplier, date_from=None, date_to=None, on_or_before=None):
    """Invoice lines from live ERP invoices (exclude migrated SATO26 docs already on the ledger)."""
    lines = SalesInvoiceLine.objects.filter(
        supplier=supplier,
        invoice__status__in=SalesInvoice.reporting_statuses(),
    ).exclude(invoice__invoice_no__startswith=LEGACY_DOC_PREFIX)
    if on_or_before is not None:
        lines = lines.filter(invoice__issue_date__lte=on_or_before)
    if date_from:
        lines = lines.filter(service_date__gte=date_from)
    if date_to:
        lines = lines.filter(service_date__lte=date_to)
    return lines


def _append_live_invoice_line_rows(rows, supplier, date_from=None, date_to=None, today=None):
    today = today or date.today()
    lines = (
        _live_supplier_invoice_lines_qs(supplier)
        .select_related(
            "invoice",
            "service_type",
            "destination",
            "service_instance__service_type",
        )
        .prefetch_related("service_type__field_definitions")
        .order_by("service_date", "invoice__issue_date", "invoice__created_at", "id")
    )
    for line in lines:
        if not _line_visible_by_report_dates(line, date_from, date_to):
            continue
        inv = line.invoice
        svc_date = line.effective_service_date()
        amt = line.line_cost_amount_usd().quantize(Decimal("0.01"))
        st = line.service_type
        if not st and line.service_instance_id and line.service_instance:
            st = line.service_instance.service_type
        rows.append(
            {
                "date": svc_date,
                "type": st.name if st else "Service",
                "description": line.supplier_statement_description(),
                "destination": line.destination.name if line.destination_id else "—",
                "ref": inv.invoice_no,
                "ref_url": invoice_ref_url(inv.id),
                "debit": Decimal("0.00"),
                "credit": amt,
                "sort_seq": inv.created_at,
                "sort_id": f"live-line-{line.id}",
                "is_pending": bool(svc_date and svc_date > today),
            }
        )


def _append_live_payment_rows(rows, supplier, date_from=None, date_to=None):
    for pay in _live_supplier_payments_qs(
        supplier, date_from, date_to, Payment.Direction.OUT
    ).order_by("date", "created_at"):
        rows.append(
            {
                "date": pay.date,
                "type": "Payment",
                "description": _payment_supplier_description(pay),
                "destination": "—",
                "ref": pay.receipt_no,
                "ref_url": None,
                "debit": pay.amount,
                "credit": Decimal("0.00"),
                "sort_seq": pay.created_at,
                "sort_id": f"live-pay-{pay.id}",
                "is_pending": False,
            }
        )

    for pay in _live_supplier_payments_qs(
        supplier, date_from, date_to, Payment.Direction.IN
    ).order_by("date", "created_at"):
        rows.append(
            {
                "date": pay.date,
                "type": "Receipt",
                "description": _payment_supplier_description(pay),
                "destination": "—",
                "ref": pay.receipt_no,
                "ref_url": None,
                "debit": pay.amount,
                "credit": Decimal("0.00"),
                "sort_seq": pay.created_at,
                "sort_id": f"live-pay-in-{pay.id}",
                "is_pending": False,
            }
        )


def supplier_ledger_balance(
    supplier,
    *,
    date_from=None,
    date_to=None,
    on_or_before=None,
) -> Decimal:
    """Net AP from legacy 401* journal lines: sum(C) - sum(D)."""
    credits = Decimal("0.00")
    debits = Decimal("0.00")
    for line in _supplier_ledger_qs(supplier, date_from, date_to, on_or_before):
        if line.dc == SupplierLedgerLine.DC.CREDIT:
            credits += line.amount
        else:
            debits += line.amount
    return credits - debits


def live_supplier_purchase_credits(
    supplier,
    *,
    date_from=None,
    date_to=None,
    on_or_before=None,
) -> Decimal:
    lines = _live_supplier_invoice_lines_qs(
        supplier, date_from=date_from, date_to=date_to, on_or_before=on_or_before
    )
    return sum((line.line_cost_amount_usd() for line in lines), Decimal("0.00"))


def live_supplier_payment_net(
    supplier,
    *,
    date_from=None,
    date_to=None,
    on_or_before=None,
) -> Decimal:
    """Payments that reduce AP (OUT + IN), live ERP only."""
    out_total = sum(
        (
            p.amount
            for p in _live_supplier_payments_qs(
                supplier, date_from, date_to, Payment.Direction.OUT, on_or_before=on_or_before
            )
        ),
        Decimal("0.00"),
    )
    in_total = sum(
        (
            p.amount
            for p in _live_supplier_payments_qs(
                supplier, date_from, date_to, Payment.Direction.IN, on_or_before=on_or_before
            )
        ),
        Decimal("0.00"),
    )
    return out_total + in_total


def supplier_purchase_credits(
    supplier,
    *,
    date_from=None,
    date_to=None,
    on_or_before=None,
) -> Decimal:
    """Total supplier credits for movement reports (legacy ledger + live invoice line costs)."""
    credits = Decimal("0.00")
    if supplier_has_ledger(supplier):
        for line in _supplier_ledger_qs(supplier, date_from, date_to, on_or_before):
            if line.dc == SupplierLedgerLine.DC.CREDIT:
                credits += line.amount

    credits += live_supplier_purchase_credits(
        supplier, date_from=date_from, date_to=date_to, on_or_before=on_or_before
    )
    return credits


def build_supplier_statement_rows(supplier, date_from=None, date_to=None):
    """Legacy 401* journal lines plus live invoice costs and treasury payments."""
    today = date.today()
    rows = []

    if supplier_has_ledger(supplier):
        for line in _supplier_ledger_qs(supplier, date_from, date_to):
            inv_id = _invoice_id_for_no(line.invoice_no)
            debit = line.amount.quantize(Decimal("0.01")) if line.dc == SupplierLedgerLine.DC.DEBIT else Decimal("0.00")
            credit = line.amount.quantize(Decimal("0.01")) if line.dc == SupplierLedgerLine.DC.CREDIT else Decimal("0.00")
            rows.append(
                {
                    "date": line.line_date,
                    "type": _ledger_row_type(line),
                    "description": line.description or line.invoice_no or f"JV {line.legacy_jvno}",
                    "destination": "—",
                    "ref": line.invoice_no or f"{line.journal_type}-{line.legacy_jvno}",
                    "ref_url": invoice_ref_url(inv_id) if inv_id else None,
                    "debit": debit,
                    "credit": credit,
                    "sort_seq": line.line_date,
                    "sort_id": str(line.id),
                    "is_pending": bool(line.line_date and line.line_date > today),
                }
            )

    _append_live_invoice_line_rows(rows, supplier, date_from, date_to, today)
    _append_live_payment_rows(rows, supplier, date_from, date_to)

    return sort_statement_rows(rows)
