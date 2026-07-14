"""
Period P&L totals aligned with All Clients / All Suppliers SOA.

Revenue = sum of All Clients SOA period debits  (total sellings)
COGS    = sum of All Suppliers SOA period credits (supplier service costs + any supplier money-in credits)
OPEX    = sum of posted OperatingExpense.amount_usd in the period
"""

from decimal import Decimal

from django.db.models import Sum

from accounts_core.models import Client, Supplier
from expenses.models import OperatingExpense
from reporting.statement_summary import _client_period_movement, _supplier_period_movement


def period_revenue_usd(date_from=None, date_to=None) -> Decimal:
    total = Decimal("0.00")
    for client in Client.objects.all().iterator():
        debit, _credit = _client_period_movement(client, date_from, date_to)
        total += debit
    return total.quantize(Decimal("0.01"))


def period_cogs_usd(date_from=None, date_to=None) -> Decimal:
    total = Decimal("0.00")
    for supplier in Supplier.objects.all().iterator():
        _debit, credit = _supplier_period_movement(supplier, date_from, date_to)
        total += credit
    return total.quantize(Decimal("0.01"))


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
    """Category breakdown; ordering cleared so MySQL GROUP BY matches the full OPEX total."""
    return (
        period_opex_qs(date_from, date_to)
        .values("category__code", "category__name")
        .annotate(total=Sum("amount_usd"))
        .order_by("category__code")
    )


def period_revenue_and_cogs(date_from=None, date_to=None):
    return period_revenue_usd(date_from, date_to), period_cogs_usd(date_from, date_to)
