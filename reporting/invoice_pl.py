"""
Period P&L totals — same figures as All Clients / All Suppliers SOA footers.

Revenue = All Clients SOA Total debit for the date range (all clients with period activity)
COGS    = All Suppliers SOA Total credit for the date range (all suppliers with period activity)
OPEX    = posted OperatingExpense.amount_usd with expense_date in the date range
"""

from decimal import Decimal

from django.db.models import Sum

from expenses.models import OperatingExpense
from reporting.statement_summary import (
    period_client_soa_tot_dr_cr,
    period_supplier_soa_tot_dr_cr,
)


def period_revenue_usd(date_from=None, date_to=None) -> Decimal:
    tot_dr, _tot_cr = period_client_soa_tot_dr_cr(date_from, date_to)
    return tot_dr


def period_cogs_usd(date_from=None, date_to=None) -> Decimal:
    _tot_dr, tot_cr = period_supplier_soa_tot_dr_cr(date_from, date_to)
    return tot_cr


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
