"""One-row-per-party summary builders for consolidated statements."""

from decimal import Decimal

from accounts_core.models import Client, Supplier
from purchases.models import SupplierBill
from reporting.period_movements import client_period_movements, supplier_period_movements
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
    moves = client_period_movements(date_from, date_to, client_ids=[client.id])
    return moves.get(client.id, (Decimal("0.00"), Decimal("0.00")))


def _supplier_period_movement(supplier, date_from=None, date_to=None):
    moves = supplier_period_movements(date_from, date_to, supplier_ids=[supplier.id])
    return moves.get(supplier.id, (Decimal("0.00"), Decimal("0.00")))


def build_client_summary_rows(clients, date_from=None, date_to=None, *, include_zero_balances=False):
    clients = list(clients)
    if not clients:
        return []
    client_ids = [c.id for c in clients]
    movements = client_period_movements(date_from, date_to, client_ids=client_ids)

    # One currency lookup for all clients instead of N queries.
    curr_by_client = {}
    inv_q = SalesInvoice.objects.filter(
        client_id__in=client_ids,
        status__in=SalesInvoice.reporting_statuses(),
    )
    if date_from:
        inv_q = inv_q.filter(issue_date__gte=date_from)
    if date_to:
        inv_q = inv_q.filter(issue_date__lte=date_to)
    for cid, currency in (
        inv_q.order_by("client_id", "-issue_date").values_list("client_id", "currency")
    ):
        if cid not in curr_by_client:
            curr_by_client[cid] = currency or "USD"

    rows = []
    for client in clients:
        debit, credit = movements.get(client.id, (Decimal("0.00"), Decimal("0.00")))
        # Match per-client SOA: no lines in the selected period → omit from All Clients.
        if debit == 0 and credit == 0:
            continue
        # Period balance (same date filter as tot debit/credit).
        # Balance debit = they owe you; balance credit = credit balance (you owe them).
        period_balance = debit - credit
        if abs(period_balance) < Decimal("0.01") and not include_zero_balances:
            continue
        bal_dr, bal_cr = _split_balance_dr_cr(period_balance)
        rows.append(
            {
                "account": client.client_code,
                "name": client.name_en,
                "client_id": client.id,
                "curr": curr_by_client.get(client.id, "USD"),
                "tot_dr": debit,
                "tot_cr": credit,
                "bal_dr": bal_dr,
                "bal_cr": bal_cr,
                "net_balance": period_balance,
            }
        )
    return rows


def build_supplier_summary_rows(suppliers, date_from=None, date_to=None, *, include_zero_balances=False):
    suppliers = list(suppliers)
    if not suppliers:
        return []
    supplier_ids = [s.id for s in suppliers]
    movements = supplier_period_movements(date_from, date_to, supplier_ids=supplier_ids)

    curr_by_supplier = {}
    bill_q = SupplierBill.objects.filter(
        supplier_id__in=supplier_ids,
        status=SupplierBill.Status.POSTED,
    )
    if date_from:
        bill_q = bill_q.filter(bill_date__gte=date_from)
    if date_to:
        bill_q = bill_q.filter(bill_date__lte=date_to)
    for sid, currency in bill_q.order_by("supplier_id", "-bill_date").values_list("supplier_id", "currency"):
        if sid not in curr_by_supplier:
            curr_by_supplier[sid] = currency

    rows = []
    for supplier in suppliers:
        debit, credit = movements.get(supplier.id, (Decimal("0.00"), Decimal("0.00")))
        if debit == 0 and credit == 0:
            continue
        period_balance = debit - credit
        if abs(period_balance) < Decimal("0.01") and not include_zero_balances:
            continue
        bal_dr, bal_cr = _split_balance_dr_cr(period_balance)
        rows.append(
            {
                "account": supplier.supplier_code,
                "name": supplier.name,
                "supplier_id": supplier.id,
                "curr": curr_by_supplier.get(supplier.id) or supplier.default_currency or "USD",
                "tot_dr": debit,
                "tot_cr": credit,
                "bal_dr": bal_dr,
                "bal_cr": bal_cr,
                "net_balance": period_balance,
            }
        )
    return rows


def summarize_totals(rows):
    """Footer totals: sum balance debit and balance credit separately (do not net them)."""
    tot_dr = sum((r["tot_dr"] for r in rows), Decimal("0.00"))
    tot_cr = sum((r["tot_cr"] for r in rows), Decimal("0.00"))
    bal_dr = sum((r["bal_dr"] for r in rows), Decimal("0.00"))
    bal_cr = sum((r["bal_cr"] for r in rows), Decimal("0.00"))
    net_balance = sum(
        (r.get("net_balance") if r.get("net_balance") is not None else (r["bal_dr"] - r["bal_cr"]) for r in rows),
        Decimal("0.00"),
    )
    return tot_dr, tot_cr, bal_dr, bal_cr, net_balance


def summarize_supplier_totals(rows):
    """Footer totals: sum balance debit and balance credit separately (do not net them)."""
    tot_dr = sum((r["tot_dr"] for r in rows), Decimal("0.00"))
    tot_cr = sum((r["tot_cr"] for r in rows), Decimal("0.00"))
    bal_dr = sum((r["bal_dr"] for r in rows), Decimal("0.00"))
    bal_cr = sum((r["bal_cr"] for r in rows), Decimal("0.00"))
    net_balance = sum(
        (r.get("net_balance") if r.get("net_balance") is not None else (r["bal_dr"] - r["bal_cr"]) for r in rows),
        Decimal("0.00"),
    )
    return tot_dr, tot_cr, bal_dr, bal_cr, net_balance
