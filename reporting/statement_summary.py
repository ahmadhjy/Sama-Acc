"""One-row-per-party summary builders for consolidated statements."""

from datetime import timedelta
from decimal import Decimal

from accounts_core.models import Client, Supplier
from purchases.models import SupplierBill
from reporting.balances import supplier_ap_balance
from reporting.client_statement_rows import build_client_statement_rows
from reporting.supplier_statement_rows import build_supplier_statement_rows
from sales.models import SalesInvoice


def _split_balance_dr_cr(net):
    if net > 0:
        return net, Decimal("0.00")
    if net < 0:
        return Decimal("0.00"), -net
    return Decimal("0.00"), Decimal("0.00")


def _split_movement_balance_dr_cr(debit, credit):
    """Put period movement difference in debit or credit balance column, not both."""
    debit = debit or Decimal("0.00")
    credit = credit or Decimal("0.00")
    if debit > credit:
        return debit - credit, Decimal("0.00")
    if credit > debit:
        return Decimal("0.00"), credit - debit
    return Decimal("0.00"), Decimal("0.00")


def profit_summary_row(label, amount, curr="USD"):
    """Trial-balance summary line for P&L figures (profit in credit, loss in debit)."""
    amt = amount or Decimal("0.00")
    if amt >= 0:
        return {
            "account": "",
            "name": label,
            "curr": curr,
            "tot_dr": Decimal("0.00"),
            "tot_cr": amt,
            "bal_dr": Decimal("0.00"),
            "bal_cr": amt,
            "is_summary": True,
        }
    loss = -amt
    return {
        "account": "",
        "name": label,
        "curr": curr,
        "tot_dr": loss,
        "tot_cr": Decimal("0.00"),
        "bal_dr": loss,
        "bal_cr": Decimal("0.00"),
        "is_summary": True,
    }


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


def build_client_summary_rows(clients, date_from=None, date_to=None, *, include_zero_balances=False):
    rows = []
    for client in clients:
        debit, credit = _client_period_movement(client, date_from, date_to)
        # Match per-client SOA: no lines in the selected period → omit from All Clients.
        if debit == 0 and credit == 0:
            continue
        # Period balance (same date filter as tot debit/credit), not lifetime closing.
        period_balance = debit - credit
        if abs(period_balance) < Decimal("0.01") and not include_zero_balances:
            continue
        inv_q = SalesInvoice.objects.filter(client=client, status__in=SalesInvoice.reporting_statuses())
        if date_from:
            inv_q = inv_q.filter(issue_date__gte=date_from)
        if date_to:
            inv_q = inv_q.filter(issue_date__lte=date_to)
        row_curr = inv_q.order_by("-issue_date").values_list("currency", flat=True).first() or "USD"
        bal_dr, bal_cr = _split_balance_dr_cr(period_balance)
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
                "net_balance": period_balance,
            }
        )
    return rows


def build_supplier_summary_rows(suppliers, date_from=None, date_to=None, *, include_zero_balances=False):
    day_before = (date_from - timedelta(days=1)) if date_from else None
    rows = []
    for supplier in suppliers:
        opening = supplier_ap_balance(supplier, day_before) if date_from else Decimal("0.00")
        debit, credit = _supplier_period_movement(supplier, date_from, date_to)
        closing = opening + credit - debit
        # Match per-supplier SOA: no lines in the selected period → omit from All Suppliers.
        if debit == 0 and credit == 0:
            continue
        # Zero closing balance hidden by default.
        if abs(closing) < Decimal("0.01") and not include_zero_balances:
            continue
        bill_q = SupplierBill.objects.filter(supplier=supplier, status=SupplierBill.Status.POSTED)
        if date_from:
            bill_q = bill_q.filter(bill_date__gte=date_from)
        if date_to:
            bill_q = bill_q.filter(bill_date__lte=date_to)
        row_curr = bill_q.order_by("-bill_date").values_list("currency", flat=True).first()
        if not row_curr:
            row_curr = supplier.default_currency or "USD"
        bal_dr, bal_cr = _split_movement_balance_dr_cr(debit, credit)
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
                "net_balance": bal_dr + bal_cr,
            }
        )
    return rows


def summarize_totals(rows):
    """Footer totals for client summaries: net DR/CR balances into a single column."""
    tot_dr = sum((r["tot_dr"] for r in rows), Decimal("0.00"))
    tot_cr = sum((r["tot_cr"] for r in rows), Decimal("0.00"))
    net_balance = sum((r.get("net_balance") or (r["bal_dr"] - r["bal_cr"]) for r in rows), Decimal("0.00"))
    bal_dr, bal_cr = _split_balance_dr_cr(net_balance)
    return tot_dr, tot_cr, bal_dr, bal_cr, net_balance


def summarize_supplier_totals(rows):
    tot_dr = sum((r["tot_dr"] for r in rows), Decimal("0.00"))
    tot_cr = sum((r["tot_cr"] for r in rows), Decimal("0.00"))
    bal_dr, bal_cr = _split_movement_balance_dr_cr(tot_dr, tot_cr)
    total_balance = bal_dr + bal_cr
    return tot_dr, tot_cr, bal_dr, bal_cr, total_balance
