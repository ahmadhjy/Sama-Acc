from datetime import date

from accounts_core.branding import get_company_branding


def pdf_branding(request):
    ctx = {
        "is_pdf": request.GET.get("format") == "pdf",
        "company": get_company_branding(request),
        "pdf_generated_on": date.today(),
    }
    if not ctx["is_pdf"]:
        path = request.path.rstrip("/") or "/"
        if path == "/" or path.startswith("/reporting"):
            from reporting.date_ranges import resolve_report_dates
            from reporting.hub_nav import build_hub_nav

            ctx.update(build_hub_nav(request))
            df, dt, period_label = resolve_report_dates(request)
            ctx["date_from"] = df
            ctx["date_to"] = dt
            ctx["period_label"] = period_label
    return ctx
