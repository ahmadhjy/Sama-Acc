"""
Period P&L totals aligned with All Clients / All Suppliers SOA.

Revenue = sum of All Clients SOA period debits  (total sellings)
COGS    = sum of All Suppliers SOA period credits (supplier service costs + any supplier money-in credits)

This matches the Totals row on those SOA pages when "Show zero balances" is on,
so dashboard / income statement numbers are understandable against SOA.
"""

from decimal import Decimal

from accounts_core.models import Client, Supplier
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


def period_revenue_and_cogs(date_from=None, date_to=None):
    return period_revenue_usd(date_from, date_to), period_cogs_usd(date_from, date_to)
