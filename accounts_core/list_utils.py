from datetime import date, datetime


def parse_post_date(value, default=None):
    """Parse YYYY-MM-DD from a form POST value into a date."""
    if value is None or value == "":
        return default
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Invalid date. Use YYYY-MM-DD.") from exc


def parse_date(req, key):
    v = req.GET.get(key)
    if not v:
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%d").date()
    except ValueError:
        return None


def invoice_search_filters(qs, request):
    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q

        qs = qs.filter(Q(invoice_no__icontains=q) | Q(client__name_en__icontains=q) | Q(client__client_code__icontains=q))
    d0 = parse_date(request, "date_from")
    d1 = parse_date(request, "date_to")
    if d0:
        qs = qs.filter(issue_date__gte=d0)
    if d1:
        qs = qs.filter(issue_date__lte=d1)
    return qs


def payment_search_filters(qs, request):
    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q

        qs = qs.filter(
            Q(receipt_no__icontains=q)
            | Q(reference__icontains=q)
            | Q(party_name__icontains=q)
            | Q(client__name_en__icontains=q)
            | Q(supplier__name__icontains=q)
        )
    d0 = parse_date(request, "date_from")
    d1 = parse_date(request, "date_to")
    if d0:
        qs = qs.filter(date__gte=d0)
    if d1:
        qs = qs.filter(date__lte=d1)
    return qs


def bill_search_filters(qs, request):
    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q

        qs = qs.filter(Q(bill_no__icontains=q) | Q(supplier__name__icontains=q))
    d0 = parse_date(request, "date_from")
    d1 = parse_date(request, "date_to")
    if d0:
        qs = qs.filter(bill_date__gte=d0)
    if d1:
        qs = qs.filter(bill_date__lte=d1)
    return qs


def client_list_filters(qs, request):
    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q

        qs = qs.filter(
            Q(name_en__icontains=q) | Q(name_ar__icontains=q) | Q(client_code__icontains=q) | Q(email__icontains=q)
        )
    return qs


def supplier_list_filters(qs, request):
    if request.GET.get("show_inactive") != "1":
        qs = qs.filter(is_active=True)
    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q

        qs = qs.filter(Q(name__icontains=q) | Q(supplier_code__icontains=q) | Q(email__icontains=q))
    return qs


def service_type_list_filters(qs, request):
    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q

        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    return qs


def service_instance_list_filters(qs, request):
    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q

        qs = qs.filter(
            Q(notes__icontains=q)
            | Q(service_type__name__icontains=q)
            | Q(service_type__code__icontains=q)
            | Q(passenger__full_name_en__icontains=q)
            | Q(supplier__name__icontains=q)
        )
    d0 = parse_date(request, "date_from")
    d1 = parse_date(request, "date_to")
    if d0:
        qs = qs.filter(created_at__date__gte=d0)
    if d1:
        qs = qs.filter(created_at__date__lte=d1)
    return qs
