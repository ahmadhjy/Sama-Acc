"""
Period P&L totals from sales invoices (not SOA footers).

Revenue = sum of invoice grand_total_usd for reporting invoices with issue_date in range
COGS    = sum of line costs (qty × cost_price_usd) on those same invoices
OPEX    = posted OperatingExpense.amount_usd with expense_date in the date range

SOA totals can differ (service dates, payments, ledger) and stay on the statement pages.
"""

from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce

from expenses.models import OperatingExpense
from sales.models import SalesInvoice, SalesInvoiceLine

ZERO = Decimal("0.00")


def _period_invoices(date_from=None, date_to=None):
    qs = SalesInvoice.objects.filter(status__in=SalesInvoice.reporting_statuses())
    if date_from:
        qs = qs.filter(issue_date__gte=date_from)
    if date_to:
        qs = qs.filter(issue_date__lte=date_to)
    return qs


def period_revenue_usd(date_from=None, date_to=None) -> Decimal:
    total = _period_invoices(date_from, date_to).aggregate(t=Sum("grand_total_usd"))["t"]
    return (total or ZERO).quantize(Decimal("0.01"))


def period_cogs_usd(date_from=None, date_to=None) -> Decimal:
    cost_expr = ExpressionWrapper(
        F("qty") * Coalesce(F("cost_price_usd"), Value(ZERO)),
        output_field=DecimalField(max_digits=18, decimal_places=4),
    )
    qs = SalesInvoiceLine.objects.filter(invoice__status__in=SalesInvoice.reporting_statuses())
    if date_from:
        qs = qs.filter(invoice__issue_date__gte=date_from)
    if date_to:
        qs = qs.filter(invoice__issue_date__lte=date_to)
    total = qs.aggregate(t=Sum(cost_expr))["t"]
    return (total or ZERO).quantize(Decimal("0.01"))


def period_opex_qs(date_from=None, date_to=None):
    """Posted operating expenses in the period (ordering cleared for safe aggregation)."""
    qs = OperatingExpense.objects.filter(status=OperatingExpense.Status.POSTED).order_by()
    if date_from:
        qs = qs.filter(expense_date__gte=date_from)
    if date_to:
        qs = qs.filter(expense_date__lte=date_to)
    return qs


def period_opex_usd(date_from=None, date_to=None) -> Decimal:
    return (period_opex_qs(date_from, date_to).aggregate(t=Sum("amount_usd"))["t"] or Decimal("0.00")).quantize(
        Decimal("0.01")
    )


def period_opex_by_category(date_from=None, date_to=None):
    """Category breakdown; ordering cleared so GROUP BY matches the full OPEX total."""
    return (
        period_opex_qs(date_from, date_to)
        .values("category__code", "category__name")
        .annotate(total=Sum("amount_usd"))
        .order_by("category__code")
    )


def period_revenue_and_cogs(date_from=None, date_to=None):
    return period_revenue_usd(date_from, date_to), period_cogs_usd(date_from, date_to)
