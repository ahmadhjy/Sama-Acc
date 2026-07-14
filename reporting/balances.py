from decimal import Decimal

from django.db.models import Sum

from reporting.payment_amounts import payment_usd_amount
from reporting.supplier_statement_rows import (
    live_supplier_payment_net,
    live_supplier_purchase_credits,
    supplier_has_ledger,
    supplier_ledger_balance,
    supplier_purchase_credits,
)
from sales.models import SalesInvoice
from treasury.models import Payment


def _client_payments_qs(client, date_from=None, date_to=None, on_or_before=None, direction=None):
    from reporting.client_statement_rows import _client_payments_qs as qs_fn

    qs = qs_fn(client, date_from=date_from, date_to=date_to, direction=direction)
    if on_or_before is not None:
        qs = qs.filter(date__lte=on_or_before)
    return qs


def client_ar_balance(client, on_or_before):
    if on_or_before is None:
        return Decimal("0.00")
    inv = (
        SalesInvoice.objects.filter(
            client=client,
            status__in=SalesInvoice.reporting_statuses(),
            issue_date__lte=on_or_before,
        ).aggregate(t=Sum("grand_total_usd"))["t"]
        or Decimal("0.00")
    )
    payments_in = sum(
        (payment_usd_amount(p) for p in _client_payments_qs(client, on_or_before=on_or_before, direction=Payment.Direction.IN)),
        Decimal("0.00"),
    )
    payments_out = sum(
        (payment_usd_amount(p) for p in _client_payments_qs(client, on_or_before=on_or_before, direction=Payment.Direction.OUT)),
        Decimal("0.00"),
    )
    return inv - payments_in + payments_out


def supplier_ap_balance(supplier, on_or_before):
    if on_or_before is None:
        return Decimal("0.00")
    balance = Decimal("0.00")
    if supplier_has_ledger(supplier):
        # Ledger net excluding SI rows replaced by editable SalesInvoiceLine costs.
        balance += supplier_ledger_balance(supplier, on_or_before=on_or_before)
    # All editable invoice line costs (INV- and imported SATO26-)
    # + live PAY-: money out reduces AP, money in from supplier increases AP.
    balance += live_supplier_purchase_credits(supplier, on_or_before=on_or_before)
    balance -= live_supplier_payment_net(supplier, on_or_before=on_or_before)
    return balance


def supplier_line_purchases(supplier, date_from=None, date_to=None):
    return supplier_purchase_credits(supplier, date_from=date_from, date_to=date_to)
