from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Q

from sales.models import SalesInvoice, SalesInvoiceLine


def _date_filter_qs(qs, date_field, date_from, date_to):
    if date_from:
        qs = qs.filter(**{f"{date_field}__gte": date_from})
    if date_to:
        qs = qs.filter(**{f"{date_field}__lte": date_to})
    return qs


def _employee_line_qs(employee, date_from=None, date_to=None):
    qs = SalesInvoiceLine.objects.filter(
        line_employee=employee,
        invoice__status=SalesInvoice.Status.POSTED,
    ).select_related("invoice", "invoice__client")
    return _date_filter_qs(qs, "invoice__issue_date", date_from, date_to)


def _line_selling_usd(line):
    qty = line.qty or Decimal("0")
    sell = line.sell_price_usd or Decimal("0")
    discount = line.line_discount_usd or Decimal("0")
    return qty * sell - discount


def _line_cost_usd(line):
    return (line.qty or Decimal("0")) * (line.cost_price_usd or Decimal("0"))


def build_brief_report(employee, date_from=None, date_to=None):
    line_invoice_ids = SalesInvoiceLine.objects.filter(line_employee=employee).values_list("invoice_id", flat=True)
    invoices = SalesInvoice.objects.filter(
        Q(sales_employee=employee) | Q(pk__in=line_invoice_ids),
        status=SalesInvoice.Status.POSTED,
    ).distinct()
    invoices = _date_filter_qs(invoices, "issue_date", date_from, date_to)
    lines = _employee_line_qs(employee, date_from, date_to)

    revenue = Decimal("0.00")
    for inv in invoices:
        revenue += inv.grand_total_usd or Decimal("0.00")

    cost_usd = Decimal("0.00")
    for line in lines:
        cost_usd += _line_cost_usd(line)

    client_ids = set(invoices.values_list("client_id", flat=True))
    return {
        "employee": employee,
        "date_from": date_from,
        "date_to": date_to,
        "total_services": lines.count(),
        "total_clients": len(client_ids),
        "total_invoices": invoices.count(),
        "total_revenue": revenue,
        "total_profit": revenue - cost_usd,
        "total_cost": cost_usd,
    }


def build_detailed_report(employee, date_from=None, date_to=None):
    """
    One row per invoice:
    - Main salesperson on invoice → whole invoice selling, cost, profit (USD).
    - Line participant only → selling/cost/profit for that employee's lines only.
    """
    rows = []
    seen_invoice_ids = set()

    main_invoices = _date_filter_qs(
        SalesInvoice.objects.filter(
            sales_employee=employee,
            status=SalesInvoice.Status.POSTED,
        ).select_related("client"),
        "issue_date",
        date_from,
        date_to,
    )

    for inv in main_invoices.order_by("issue_date", "invoice_no"):
        selling = inv.grand_total_usd or Decimal("0.00")
        cost = inv.total_line_cost_usd()
        profit = selling - cost
        rows.append(
            {
                "date": inv.issue_date,
                "invoice_id": inv.id,
                "invoice_no": inv.invoice_no,
                "client_name": inv.client.name_en if inv.client_id else "",
                "selling": selling,
                "cost": cost,
                "profit": profit,
            }
        )
        seen_invoice_ids.add(inv.id)

    lines = list(_employee_line_qs(employee, date_from, date_to))
    lines_by_invoice = defaultdict(list)
    for line in lines:
        if line.invoice_id not in seen_invoice_ids:
            lines_by_invoice[line.invoice_id].append(line)

    for invoice_id in sorted(lines_by_invoice.keys(), key=lambda i: lines_by_invoice[i][0].invoice.issue_date or date.today()):
        inv_lines = lines_by_invoice[invoice_id]
        inv = inv_lines[0].invoice
        selling = sum((_line_selling_usd(ln) for ln in inv_lines), Decimal("0.00"))
        cost = sum((_line_cost_usd(ln) for ln in inv_lines), Decimal("0.00"))
        profit = selling - cost
        rows.append(
            {
                "date": inv.issue_date,
                "invoice_id": inv.id,
                "invoice_no": inv.invoice_no,
                "client_name": inv.client.name_en if inv.client_id else "",
                "selling": selling,
                "cost": cost,
                "profit": profit,
            }
        )

    rows.sort(key=lambda r: (r["date"] or date.today(), r["invoice_no"]))

    total_selling = sum((r["selling"] for r in rows), Decimal("0.00"))
    total_cost = sum((r["cost"] for r in rows), Decimal("0.00"))
    total_profit = sum((r["profit"] for r in rows), Decimal("0.00"))

    return {
        "employee": employee,
        "date_from": date_from,
        "date_to": date_to,
        "rows": rows,
        "total_selling": total_selling,
        "total_cost": total_cost,
        "total_profit": total_profit,
        "brief": build_brief_report(employee, date_from, date_to),
    }
