from datetime import date
from decimal import Decimal

from reporting.payment_amounts import payment_usd_amount
from reporting.statement_refs import invoice_ref_url, payment_ref_url
from reporting.statement_sort import sort_statement_rows
from sales.models import SalesInvoice
from treasury.models import Payment


def _client_payments_qs(client, date_from=None, date_to=None):
    qs = Payment.objects.filter(
        client=client,
        party_type=Payment.PartyType.CLIENT,
        direction=Payment.Direction.IN,
        status=Payment.Status.POSTED,
    )
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    return qs.select_related("money_account")


def _payment_statement_description(payment: Payment) -> str:
    ref_no = (payment.reference or "").strip() or "—"
    account = payment.money_account.name if payment.money_account_id else "—"
    return f"{ref_no} - {account}"


def build_client_statement_rows(client, date_from=None, date_to=None):
    """One debit row per posted invoice service line; one credit row per posted client payment."""
    invoices = (
        SalesInvoice.objects.filter(client=client, status=SalesInvoice.Status.POSTED)
        .prefetch_related(
            "lines__service_type__field_definitions",
            "lines__service_instance__service_type__field_definitions",
        )
    )
    rows = []
    for inv in invoices.order_by("issue_date", "created_at"):
        for line in inv.lines.select_related("destination").all():
            line_date = line.effective_service_date()
            if date_from and line_date and line_date < date_from:
                continue
            if date_to and line_date and line_date > date_to:
                continue
            amt = line.line_selling_amount_usd().quantize(Decimal("0.01"))
            st = line.service_type
            if not st and line.service_instance_id and line.service_instance:
                st = line.service_instance.service_type
            rows.append(
                {
                    "date": line_date,
                    "type": st.name if st else "Service",
                    "description": line.statement_description(),
                    "ref": inv.invoice_no,
                    "ref_url": invoice_ref_url(inv.id),
                    "debit": amt,
                    "credit": Decimal("0.00"),
                    "sort_seq": inv.created_at,
                    "sort_id": str(line.id),
                }
            )

    for pay in _client_payments_qs(client, date_from, date_to).order_by("date", "created_at"):
        rows.append(
            {
                "date": pay.date,
                "type": "Payment",
                "description": _payment_statement_description(pay),
                "ref": pay.receipt_no,
                "ref_url": payment_ref_url(pay.id),
                "debit": Decimal("0.00"),
                "credit": payment_usd_amount(pay),
                "sort_seq": pay.created_at,
                "sort_id": str(pay.id),
            }
        )

    return sort_statement_rows(rows)
