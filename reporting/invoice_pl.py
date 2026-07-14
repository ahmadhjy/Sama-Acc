"""Period P&L totals from sales invoices — same basis as the invoice form."""

from decimal import Decimal

from django.db.models import Sum

from sales.models import SalesInvoice, SalesInvoiceLine


def period_invoices_qs(date_from=None, date_to=None):
    """Active invoices in the period (by issue date)."""
    qs = SalesInvoice.objects.filter(status__in=SalesInvoice.reporting_statuses())
    if date_from:
        qs = qs.filter(issue_date__gte=date_from)
    if date_to:
        qs = qs.filter(issue_date__lte=date_to)
    return qs


def period_revenue_usd(date_from=None, date_to=None) -> Decimal:
    """Sum of invoice selling totals (Total selling on each invoice) in USD."""
    return (
        period_invoices_qs(date_from, date_to).aggregate(t=Sum("grand_total_usd"))["t"]
        or Decimal("0.00")
    )


def period_cogs_usd(date_from=None, date_to=None) -> Decimal:
    """
    Sum of service-line costs for those same invoices (Total cost on each invoice) in USD.

    Uses invoice issue date so Revenue and COGS always cover the same documents.
    """
    lines = SalesInvoiceLine.objects.filter(
        invoice__status__in=SalesInvoice.reporting_statuses(),
    ).only("qty", "cost_price_usd")
    if date_from:
        lines = lines.filter(invoice__issue_date__gte=date_from)
    if date_to:
        lines = lines.filter(invoice__issue_date__lte=date_to)
    total = Decimal("0.00")
    for line in lines.iterator():
        total += line.line_cost_amount_usd()
    return total.quantize(Decimal("0.01"))


def period_revenue_and_cogs(date_from=None, date_to=None):
    return period_revenue_usd(date_from, date_to), period_cogs_usd(date_from, date_to)
