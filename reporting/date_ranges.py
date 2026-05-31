from datetime import date, timedelta


def resolve_report_dates(request):
    """Return (date_from, date_to, preset_label) from GET params."""
    preset = (request.GET.get("preset") or "").strip().lower()
    today = date.today()

    if preset == "today":
        return today, today, "Today"
    if preset == "week":
        start = today - timedelta(days=today.weekday())
        return start, today, "This week"
    if preset == "month":
        return today.replace(day=1), today, "This month"
    if preset == "year":
        return today.replace(month=1, day=1), today, "This year"

    from accounts_core.list_utils import parse_date

    df = parse_date(request, "date_from")
    dt = parse_date(request, "date_to")
    label = "Custom range"
    if df and dt:
        label = f"{df} – {dt}"
    elif df:
        label = f"From {df}"
    elif dt:
        label = f"Until {dt}"
    return df, dt, label
