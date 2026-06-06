from datetime import date, timedelta


def current_year_bounds():
    """January 1 through December 31 of the current calendar year."""
    today = date.today()
    return date(today.year, 1, 1), date(today.year, 12, 31)


def default_filter_query():
    """Query string for clear-filters / year default (no preset)."""
    df, dt = current_year_bounds()
    return f"date_from={df.isoformat()}&date_to={dt.isoformat()}"


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
        y_start, y_end = current_year_bounds()
        return y_start, y_end, f"Year {today.year}"

    from accounts_core.list_utils import parse_date

    df = parse_date(request, "date_from")
    dt = parse_date(request, "date_to")
    if df or dt:
        label = "Custom range"
        if df and dt:
            label = f"{df} – {dt}"
        elif df:
            label = f"From {df}"
        elif dt:
            label = f"Until {dt}"
        return df, dt, label

    y_start, y_end = current_year_bounds()
    return y_start, y_end, f"Year {today.year}"
