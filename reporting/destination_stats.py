"""Destination analytics for dashboard."""

from collections import defaultdict
from decimal import Decimal

from catalog.models import Destination
from sales.models import SalesInvoice, SalesInvoiceLine


def build_destination_stats(date_from=None, date_to=None):
    from django.db.models.functions import Coalesce

    lines = (
        SalesInvoiceLine.objects.filter(
            invoice__status__in=SalesInvoice.reporting_statuses(),
            destination_id__isnull=False,
        )
        .annotate(line_date=Coalesce("service_date", "invoice__issue_date"))
        .select_related("destination", "service_type", "supplier", "invoice", "invoice__client")
    )

    if date_from:
        lines = lines.filter(line_date__gte=date_from)
    if date_to:
        lines = lines.filter(line_date__lte=date_to)

    buckets = defaultdict(
        lambda: {
            "destination": None,
            "country": "",
            "line_count": 0,
            "invoice_count": 0,
            "client_count": 0,
            "sales": Decimal("0.00"),
            "cost": Decimal("0.00"),
            "profit": Decimal("0.00"),
            "service_types": set(),
            "top_clients": defaultdict(lambda: Decimal("0.00")),
            "top_suppliers": defaultdict(lambda: Decimal("0.00")),
            "_invoices": set(),
            "_clients": set(),
        }
    )

    for line in lines:
        dest = line.destination
        if not dest:
            continue
        key = str(dest.id)
        row = buckets[key]
        row["destination"] = dest
        row["country"] = dest.country or ""
        row["line_count"] += 1
        row["_invoices"].add(line.invoice_id)
        if line.invoice and line.invoice.client_id:
            row["_clients"].add(line.invoice.client_id)
            client_name = line.invoice.client.name_en
            row["top_clients"][client_name] += line.line_selling_amount_usd()
        if line.service_type_id:
            row["service_types"].add(line.service_type.name)
        if line.supplier_id:
            row["top_suppliers"][line.supplier.name] += line.line_cost_amount_usd()
        sales = line.line_selling_amount_usd()
        cost = line.line_cost_amount_usd()
        row["sales"] += sales
        row["cost"] += cost
        row["profit"] += sales - cost

    rows = []
    for data in buckets.values():
        data["invoice_count"] = len(data["_invoices"])
        data["client_count"] = len(data["_clients"])
        del data["_invoices"]
        del data["_clients"]
        data["service_types"] = sorted(data["service_types"])
        data["top_clients"] = sorted(data["top_clients"].items(), key=lambda x: x[1], reverse=True)[:5]
        data["top_suppliers"] = sorted(data["top_suppliers"].items(), key=lambda x: x[1], reverse=True)[:5]
        rows.append(data)

    rows.sort(key=lambda r: r["sales"], reverse=True)

    chart_labels = [r["destination"].name for r in rows[:12]]
    chart_sales = [float(r["sales"]) for r in rows[:12]]
    chart_profit = [float(r["profit"]) for r in rows[:12]]

    totals = {
        "destinations": len(rows),
        "lines": sum(r["line_count"] for r in rows),
        "sales": sum((r["sales"] for r in rows), Decimal("0.00")),
        "cost": sum((r["cost"] for r in rows), Decimal("0.00")),
        "profit": sum((r["profit"] for r in rows), Decimal("0.00")),
    }

    return {
        "destination_stats": rows,
        "destination_totals": totals,
        "chart_destination_labels": chart_labels,
        "chart_destination_sales": chart_sales,
        "chart_destination_profit": chart_profit,
    }
