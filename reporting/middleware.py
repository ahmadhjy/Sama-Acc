from django.http import HttpResponseRedirect
from django.urls import reverse


class ReportDateDefaultsMiddleware:
    """Redirect dashboard/report GET requests to the current-year date range."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "GET" and request.GET.get("format") not in ("pdf", "xlsx"):
            path = request.path.rstrip("/") or "/"
            if path == "/" or path.startswith("/reporting"):
                has_dates = request.GET.get("date_from") or request.GET.get("date_to")
                has_preset = request.GET.get("preset")
                if not has_dates and not has_preset:
                    from reporting.date_ranges import current_year_bounds

                    df, dt = current_year_bounds()
                    params = request.GET.copy()
                    params["date_from"] = df.isoformat()
                    params["date_to"] = dt.isoformat()
                    qs = params.urlencode()
                    target = request.path if request.path.endswith("/") or path == "/" else request.path
                    return HttpResponseRedirect(f"{target}?{qs}" if qs else target)
        return self.get_response(request)
