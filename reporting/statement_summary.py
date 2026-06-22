"""One-row-per-party summary builders for consolidated statements."""

from datetime import date, timedelta
from decimal import Decimal

from accounts_core.models import Client, Supplier
from purchases.models import SupplierBill
from reporting.balances import client_ar_balance, supplier_ap_balance
from reporting.client_statement_rows import build_client_statement_rows
from reporting.supplier_statement_rows import build_supplier_statement_rows
from sales.models import SalesInvoice


def _split_balance_dr_cr(net):
    if net > 0:
        return net, Decimal("0.00")
    if net < 0:
        return Decimal("0.00"), -net
    return Decimal("0.00"), Decimal("0.00")


def _client_period_movement(client, date_from=None, date_to=None):
    sub = build_client_statement_rows(client, date_from, date_to)
    debit = sum((r["debit"] for r in sub), Decimal("0.00"))
    credit = sum((r["credit"] for r in sub), Decimal("0.00"))
    return debit, credit


def _supplier_period_movement(supplier, date_from=None, date_to=None):
    sub = build_supplier_statement_rows(supplier, date_from, date_to)
    debit = sum((r["debit"] for r in sub), Decimal("0.00"))
    credit = sum((r["credit"] for r in sub), Decimal("0.00"))
    return debit, credit


def build_client_summary_rows(clients, date_from=None, date_to=None):
    day_before = (date_from - timedelta(days=1)) if date_from else None
    rows = []
    for client in clients:
        opening = client_ar_balance(client, day_before) if date_from else Decimal("0.00")
        debit, credit = _client_period_movement(client, date_from, date_to)
        closing = opening + debit - credit
        if debit == 0 and credit == 0 and opening == 0 and closing == 0:
            continue
        inv_q = SalesInvoice.objects.filter(client=client, status=SalesInvoice.Status.POSTED)
        if date_from:
            inv_q = inv_q.filter(issue_date__gte=date_from)
        if date_to:
            inv_q = inv_q.filter(issue_date__lte=date_to)
        row_curr = inv_q.order_by("-issue_date").values_list("currency", flat=True).first() or "USD"
        bal_dr, bal_cr = _split_balance_dr_cr(closing)
        rows.append(
            {
                "account": client.client_code,
                "name": client.name_en,
                "client_id": client.id,
                "curr": row_curr,
                "tot_dr": debit,
                "tot_cr": credit,
                "bal_dr": bal_dr,
                "bal_cr": bal_cr,
                "net_balance": closing,
            }
        )
    return rows


def build_supplier_summary_rows(suppliers, date_from=None, date_to=None):
    day_before = (date_from - timedelta(days=1)) if date_from else None
    rows = []
    for supplier in suppliers:
        opening = supplier_ap_balance(supplier, day_before) if date_from else Decimal("0.00")
        debit, credit = _supplier_period_movement(supplier, date_from, date_to)
        closing = opening + credit - debit
        if debit == 0 and credit == 0 and opening == 0 and closing == 0:
            continue
        bill_q = SupplierBill.objects.filter(supplier=supplier, status=SupplierBill.Status.POSTED)
        if date_from:
            bill_q = bill_q.filter(bill_date__gte=date_from)
        if date_to:
            bill_q = bill_q.filter(bill_date__lte=date_to)
        row_curr = bill_q.order_by("-bill_date").values_list("currency", flat=True).first()
        if not row_curr:
            row_curr = supplier.default_currency or "USD"
        bal_dr, bal_cr = _split_balance_dr_cr(closing)
        rows.append(
            {
                "account": supplier.supplier_code,
                "name": supplier.name,
                "supplier_id": supplier.id,
                "curr": row_curr,
                "tot_dr": debit,
                "tot_cr": credit,
                "bal_dr": bal_dr,
                "bal_cr": bal_cr,
                "net_balance": closing,
            }
        )
    return rows


def summarize_totals(rows):
    tot_dr = sum((r["tot_dr"] for r in rows), Decimal("0.00"))
    tot_cr = sum((r["tot_cr"] for r in rows), Decimal("0.00"))
    bal_dr = sum((r["bal_dr"] for r in rows), Decimal("0.00"))
    bal_cr = sum((r["bal_cr"] for r in rows), Decimal("0.00"))
    total_balance = bal_dr - bal_cr
    return tot_dr, tot_cr, bal_dr, bal_cr, total_balance
