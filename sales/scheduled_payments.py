"""Client payment schedule rows (invoice installments — not treasury cash)."""

from datetime import date

from django.db.models import Q

from accounts_core.list_utils import parse_date
from sales.models import SalesInvoice, SalesInvoiceScheduledPayment


def scheduled_payment_row_status(*, is_paid: bool, due_date: date | None, today: date) -> str:
    if is_paid:
        return "paid"
    if due_date is None:
        return "upcoming"
    days_until = (due_date - today).days
    if days_until < 0:
        return "overdue"
    if days_until == 0:
        return "today"
    return "upcoming"


def build_scheduled_payment_row(pay: SalesInvoiceScheduledPayment, *, today: date | None = None) -> dict:
    today = today or date.today()
    due = pay.due_date
    row_status = scheduled_payment_row_status(is_paid=pay.is_paid, due_date=due, today=today)
    days_until = (due - today).days if due else 0
    return {
        "id": pay.id,
        "client_name": pay.invoice.client.name_en if pay.invoice.client_id else "—",
        "invoice_id": pay.invoice_id,
        "invoice_no": pay.invoice.invoice_no,
        "amount": pay.amount,
        "currency": pay.invoice.currency,
        "due_date": due,
        "is_paid": pay.is_paid,
        "paid_at": pay.paid_at,
        "status": row_status,
        "days_until": days_until,
        "days_late": abs(days_until) if days_until < 0 else 0,
    }


def filtered_scheduled_payments_qs(request):
    schedule_status = (request.GET.get("schedule_status") or "unpaid").strip().lower()
    if schedule_status not in ("unpaid", "paid", "all"):
        schedule_status = "unpaid"

    qs = (
        SalesInvoiceScheduledPayment.objects.filter(
            invoice__status__in=SalesInvoice.reporting_statuses(),
        )
        .select_related("invoice", "invoice__client")
        .order_by("due_date", "invoice__invoice_no", "sort_order")
    )

    if schedule_status == "unpaid":
        qs = qs.filter(is_paid=False)
    elif schedule_status == "paid":
        qs = qs.filter(is_paid=True)

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(invoice__invoice_no__icontains=q)
            | Q(invoice__client__name_en__icontains=q)
            | Q(invoice__client__client_code__icontains=q)
        )

    date_from = parse_date(request, "date_from")
    date_to = parse_date(request, "date_to")
    if date_from:
        qs = qs.filter(due_date__gte=date_from)
    if date_to:
        qs = qs.filter(due_date__lte=date_to)

    return qs, schedule_status
