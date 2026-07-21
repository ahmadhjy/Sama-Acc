"""
Fast period debit/credit totals aligned with client/supplier SOA builders.

Avoids building full statement row lists when only period sums are needed.
"""

from collections import defaultdict
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce

from purchases.models import SupplierLedgerLine
from reporting.payment_amounts import payment_usd_amount
from reporting.supplier_statement_rows import LEGACY_DOC_PREFIX
from sales.models import SalesInvoice, SalesInvoiceLine
from treasury.models import Payment

ZERO = Decimal("0.00")


def _line_selling_expr():
    return ExpressionWrapper(
        F("qty") * Coalesce(F("sell_price_usd"), Value(ZERO))
        - Coalesce(F("line_discount_usd"), Value(ZERO)),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )


def _line_cost_expr():
    return ExpressionWrapper(
        F("qty") * Coalesce(F("cost_price_usd"), Value(ZERO)),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )


def _invoice_lines_dated(date_from=None, date_to=None):
    qs = SalesInvoiceLine.objects.filter(
        invoice__status__in=SalesInvoice.reporting_statuses(),
    ).annotate(line_date=Coalesce("service_date", "invoice__issue_date"))
    if date_from:
        qs = qs.filter(line_date__gte=date_from)
    if date_to:
        qs = qs.filter(line_date__lte=date_to)
    return qs


def client_period_movements(date_from=None, date_to=None, client_ids=None):
    """
    Map client_id -> (period_debit, period_credit) matching build_client_statement_rows.
    Debit = invoice line sellings + client money-out. Credit = client money-in.
    """
    debits = defaultdict(lambda: ZERO)
    credits = defaultdict(lambda: ZERO)

    lines = _invoice_lines_dated(date_from, date_to).filter(invoice__client_id__isnull=False)
    if client_ids is not None:
        lines = lines.filter(invoice__client_id__in=client_ids)
    for row in lines.values("invoice__client_id").annotate(total=Sum(_line_selling_expr())):
        cid = row["invoice__client_id"]
        if cid:
            debits[cid] += row["total"] or ZERO

    pay_qs = Payment.objects.filter(
        party_type=Payment.PartyType.CLIENT,
        status=Payment.Status.POSTED,
        client_id__isnull=False,
    )
    if client_ids is not None:
        pay_qs = pay_qs.filter(client_id__in=client_ids)
    if date_from:
        pay_qs = pay_qs.filter(date__gte=date_from)
    if date_to:
        pay_qs = pay_qs.filter(date__lte=date_to)

    for pay in pay_qs.only("client_id", "direction", "amount", "currency", "exchange_rate"):
        amt = payment_usd_amount(pay)
        if pay.direction == Payment.Direction.IN:
            credits[pay.client_id] += amt
        else:
            debits[pay.client_id] += amt

    ids = set(debits) | set(credits)
    if client_ids is not None:
        ids = ids | set(client_ids)
    return {cid: (debits[cid], credits[cid]) for cid in ids}


def supplier_period_movements(date_from=None, date_to=None, supplier_ids=None):
    """
    Map supplier_id -> (period_debit, period_credit) matching build_supplier_statement_rows.
    Credits = non-superseded ledger credits + invoice line costs + live supplier money-in.
    Debits = non-superseded ledger debits + live supplier money-out.
    """
    from django.db.models import Exists, OuterRef

    debits = defaultdict(lambda: ZERO)
    credits = defaultdict(lambda: ZERO)

    ledger = SupplierLedgerLine.objects.all()
    if supplier_ids is not None:
        ledger = ledger.filter(supplier_id__in=supplier_ids)
    if date_from:
        ledger = ledger.filter(line_date__gte=date_from)
    if date_to:
        ledger = ledger.filter(line_date__lte=date_to)

    # Skip ledger SI whenever the invoice exists in the ERP: costs then come from
    # SalesInvoiceLine (whichever supplier each line points to now).
    erp_invoice = SalesInvoice.objects.filter(
        invoice_no=OuterRef("invoice_no"),
        status__in=SalesInvoice.reporting_statuses(),
    )
    ledger = ledger.exclude(Q(journal_type="SI") & ~Q(invoice_no="") & Exists(erp_invoice))

    for row in ledger.values("supplier_id", "dc").annotate(total=Sum("amount")):
        sid = row["supplier_id"]
        if row["dc"] == SupplierLedgerLine.DC.CREDIT:
            credits[sid] += row["total"] or ZERO
        else:
            debits[sid] += row["total"] or ZERO

    cost_lines = _invoice_lines_dated(date_from, date_to).filter(supplier_id__isnull=False)
    if supplier_ids is not None:
        cost_lines = cost_lines.filter(supplier_id__in=supplier_ids)
    for row in cost_lines.values("supplier_id").annotate(total=Sum(_line_cost_expr())):
        sid = row["supplier_id"]
        if sid:
            credits[sid] += row["total"] or ZERO

    pay_qs = (
        Payment.objects.filter(
            party_type=Payment.PartyType.SUPPLIER,
            status=Payment.Status.POSTED,
            supplier_id__isnull=False,
        )
        .exclude(receipt_no__startswith=LEGACY_DOC_PREFIX)
    )
    if supplier_ids is not None:
        pay_qs = pay_qs.filter(supplier_id__in=supplier_ids)
    if date_from:
        pay_qs = pay_qs.filter(date__gte=date_from)
    if date_to:
        pay_qs = pay_qs.filter(date__lte=date_to)

    for pay in pay_qs.only("supplier_id", "direction", "amount"):
        if pay.direction == Payment.Direction.OUT:
            debits[pay.supplier_id] += pay.amount or ZERO
        else:
            credits[pay.supplier_id] += pay.amount or ZERO

    ids = set(debits) | set(credits)
    if supplier_ids is not None:
        ids = ids | set(supplier_ids)
    return {sid: (debits[sid], credits[sid]) for sid in ids}


def period_revenue_from_movements(movements) -> Decimal:
    total = sum((d for d, _c in movements.values()), ZERO)
    return total.quantize(Decimal("0.01"))


def period_cogs_from_movements(movements) -> Decimal:
    total = sum((c for _d, c in movements.values()), ZERO)
    return total.quantize(Decimal("0.01"))


def client_ar_balances_as_of(on_or_before):
    """
    Map client_id -> AR balance as of a date (same rules as client_ar_balance).
    Uses invoice issue_date totals minus money-in plus money-out.
    """
    balances = defaultdict(lambda: ZERO)
    if on_or_before is None:
        return {}

    for row in (
        SalesInvoice.objects.filter(
            status__in=SalesInvoice.reporting_statuses(),
            issue_date__lte=on_or_before,
            client_id__isnull=False,
        )
        .values("client_id")
        .annotate(total=Sum("grand_total_usd"))
    ):
        balances[row["client_id"]] += row["total"] or ZERO

    pays = Payment.objects.filter(
        party_type=Payment.PartyType.CLIENT,
        status=Payment.Status.POSTED,
        client_id__isnull=False,
        date__lte=on_or_before,
    ).only("client_id", "direction", "amount", "currency", "exchange_rate")
    for pay in pays:
        amt = payment_usd_amount(pay)
        if pay.direction == Payment.Direction.IN:
            balances[pay.client_id] -= amt
        else:
            balances[pay.client_id] += amt
    return dict(balances)


def supplier_ap_balances_as_of(on_or_before):
    """Map supplier_id -> AP balance as of a date (same sources as supplier_ap_balance)."""
    if on_or_before is None:
        return {}
    moves = supplier_period_movements(date_from=None, date_to=on_or_before)
    return {sid: (credit - debit) for sid, (debit, credit) in moves.items()}
