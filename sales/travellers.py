"""Travellers list from Ticket invoice lines with a travel-date custom field."""

from datetime import date, datetime
from decimal import Decimal

from django.db.models import Q

from accounts_core.list_utils import parse_date
from catalog.models import ServiceFieldDefinition, ServiceType
from sales.models import SalesInvoice, SalesInvoiceLine


def resolve_ticket_travel_field():
    """
    Find Ticket service type + travel-date field definition.

    Prefers label matching 'travel' + 'date'; falls back to first date field on Ticket.
    """
    ticket = (
        ServiceType.objects.filter(name__iexact="Ticket").first()
        or ServiceType.objects.filter(code__iexact="TKT").first()
        or ServiceType.objects.filter(code="1").first()
    )
    if not ticket:
        return None, None

    defs = list(
        ServiceFieldDefinition.objects.filter(service_type=ticket).order_by("order", "key")
    )
    travel_fd = None
    for fd in defs:
        label = (fd.label or "").lower()
        if "travel" in label and "date" in label:
            travel_fd = fd
            break
    if travel_fd is None:
        for fd in defs:
            if fd.field_type == ServiceFieldDefinition.FieldType.DATE:
                travel_fd = fd
                break
    return ticket, travel_fd


def _parse_travel_date(raw) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    text = str(raw).strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def build_traveller_rows(request):
    """
    Rows for the Travellers page.

    Default scope=upcoming (travel date >= today). scope=all shows all with a travel date.
    Optional date_from / date_to filter on travel date.
    """
    today = date.today()
    ticket, travel_fd = resolve_ticket_travel_field()
    scope = (request.GET.get("scope") or "upcoming").strip().lower()
    if scope not in ("upcoming", "all"):
        scope = "upcoming"
    date_from = parse_date(request, "date_from")
    date_to = parse_date(request, "date_to")
    q = (request.GET.get("q") or "").strip()

    if not ticket or not travel_fd:
        return {
            "rows": [],
            "ticket": ticket,
            "travel_field": travel_fd,
            "scope": scope,
            "today": today,
            "traveller_count": 0,
            "missing_config": True,
        }

    travel_key = travel_fd.key
    lines = (
        SalesInvoiceLine.objects.filter(
            service_type=ticket,
            invoice__status__in=SalesInvoice.reporting_statuses(),
        )
        .select_related("invoice", "invoice__client", "destination", "supplier", "service_type")
        .order_by("invoice__issue_date", "id")
    )
    if q:
        lines = lines.filter(
            Q(invoice__client__name_en__icontains=q)
            | Q(invoice__client__client_code__icontains=q)
            | Q(invoice__invoice_no__icontains=q)
        )

    rows = []
    for line in lines:
        travel = _parse_travel_date((line.line_data or {}).get(travel_key))
        if travel is None:
            continue
        if scope == "upcoming" and travel < today:
            continue
        if date_from and travel < date_from:
            continue
        if date_to and travel > date_to:
            continue
        client = line.invoice.client if line.invoice_id else None
        rows.append(
            {
                "line_id": line.id,
                "client_name": client.name_en if client else "—",
                "client_id": client.id if client else None,
                "invoice_id": line.invoice_id,
                "invoice_no": line.invoice.invoice_no if line.invoice_id else "—",
                "travel_date": travel,
                "destination": line.destination.name if line.destination_id else "—",
                "supplier": line.supplier.name if line.supplier_id else "—",
                "sell_usd": line.line_selling_amount_usd(),
                "is_past": travel < today,
                "is_today": travel == today,
            }
        )

    rows.sort(key=lambda r: (r["travel_date"], r["client_name"], r["invoice_no"]))
    return {
        "rows": rows,
        "ticket": ticket,
        "travel_field": travel_fd,
        "scope": scope,
        "today": today,
        "traveller_count": len(rows),
        "missing_config": False,
    }
