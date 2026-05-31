from datetime import date
from decimal import Decimal

from django.db.models import Q

from reporting.statement_refs import invoice_ref_url, payment_ref_url
from sales.models import SalesInvoice, SalesInvoiceLine
from treasury.models import Payment


def statement_service_date_upper(date_to=None):
    """Latest service date visible on supplier statements (not before today)."""
    today = date.today()
    if date_to is None:
        return today
    return date_to if date_to < today else today


def _supplier_payments_qs(supplier, date_from=None, date_to=None):
    qs = Payment.objects.filter(
        supplier=supplier,
        party_type=Payment.PartyType.SUPPLIER,
        direction=Payment.Direction.OUT,
        status=Payment.Status.POSTED,
    ).select_related("money_account")
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    return qs


def _payment_supplier_description(payment: Payment) -> str:
    return payment.money_account.name if payment.money_account_id else "—"


def build_supplier_statement_rows(supplier, date_from=None, date_to=None):
    """One debit row per posted invoice service line (cost); one credit per supplier payment.

    Service lines appear only once their service date has been reached (supplier SOA only).
    """
    upper = statement_service_date_upper(date_to)
    lines = (
        SalesInvoiceLine.objects.filter(
            supplier=supplier,
            invoice__status=SalesInvoice.Status.POSTED,
        )
        .select_related(
            "invoice",
            "service_type",
            "destination",
            "service_instance__service_type",
        )
        .prefetch_related("service_type__field_definitions")
    )
    if date_from:
        lines = lines.filter(
            Q(service_date__gte=date_from)
            | Q(service_date__isnull=True, invoice__issue_date__gte=date_from)
        )
    lines = lines.filter(
        Q(service_date__lte=upper)
        | Q(service_date__isnull=True, invoice__issue_date__lte=upper)
    )

    rows = []
    for line in lines.order_by("service_date", "invoice__issue_date"):
        inv = line.invoice
        amt = line.line_cost_amount_usd().quantize(Decimal("0.01"))
        st = line.service_type
        if not st and line.service_instance_id and line.service_instance:
            st = line.service_instance.service_type
        rows.append(
            {
                "date": line.effective_service_date(),
                "type": st.name if st else "Service",
                "description": line.supplier_statement_description(),
                "ref": inv.invoice_no,
                "ref_url": invoice_ref_url(inv.id),
                "debit": amt,
                "credit": Decimal("0.00"),
            }
        )

    for pay in _supplier_payments_qs(supplier, date_from, date_to).order_by("date", "created_at"):
        rows.append(
            {
                "date": pay.date,
                "type": "Payment",
                "description": _payment_supplier_description(pay),
                "ref": pay.receipt_no,
                "ref_url": payment_ref_url(pay.id),
                "debit": Decimal("0.00"),
                "credit": pay.amount,
            }
        )

    rows.sort(key=lambda x: (x["date"] or date.today(), x["type"], x["ref"]))
    return rows
