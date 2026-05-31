"""Top navigation for the combined Dashboard / Reporting hub."""

from django.urls import reverse


def _q(request):
    if not request:
        return ""
    parts = []
    for key in ("date_from", "date_to", "preset"):
        val = request.GET.get(key)
        if val:
            parts.append(f"{key}={val}")
    return ("?" + "&".join(parts)) if parts else ""


def _home_url(request, tab=None):
    if not request:
        return "/" if not tab else "/?tab=" + tab
    params = request.GET.copy()
    if tab:
        params["tab"] = tab
    else:
        params.pop("tab", None)
    qs = params.urlencode()
    return "/?" + qs if qs else "/"


def resolve_hub_section(request):
    path = request.path.rstrip("/") or "/"
    tab = request.GET.get("tab", "").lower()

    if path in ("", "/"):
        return tab if tab in ("reports",) else "overview"

    if path == "/reporting":
        return "reports"

    mapping = {
        "/reporting/activity-trial-balance": "trial",
        "/reporting/clients-trial-balance": "trial",
        "/reporting/suppliers-trial-balance": "trial",
        "/reporting/ar-aging": "receivables",
        "/reporting/statements/clients/all": "receivables",
        "/reporting/ap-aging": "payables",
        "/reporting/statements/suppliers/all": "payables",
        "/reporting/cash-movement": "cash",
        "/reporting/opex-by-category": "cash",
        "/reporting/salesman": "salesman",
    }
    for prefix, section in mapping.items():
        if path == prefix or path.startswith(prefix + "/"):
            return section
    if "/client-statement/" in path:
        return "receivables"
    if "/supplier-statement/" in path:
        return "payables"
    if "/salesman/" in path:
        return "salesman"
    return "overview"


def resolve_hub_subsection(request):
    path = request.path.rstrip("/")
    subs = {
        "/reporting/activity-trial-balance": "activity_tb",
        "/reporting/clients-trial-balance": "clients_tb",
        "/reporting/suppliers-trial-balance": "suppliers_tb",
        "/reporting/ar-aging": "ar_aging",
        "/reporting/statements/clients/all": "all_clients",
        "/reporting/ap-aging": "ap_aging",
        "/reporting/statements/suppliers/all": "all_suppliers",
        "/reporting/cash-movement": "cash",
        "/reporting/opex-by-category": "opex",
        "/reporting/salesman": "salesman_home",
    }
    for prefix, sub in subs.items():
        if path == prefix or path.startswith(prefix + "/"):
            return sub
    if "/client-statement/" in path:
        return "client_statement"
    if "/supplier-statement/" in path:
        return "supplier_statement"
    if path.endswith("/brief"):
        return "salesman_brief"
    if path.endswith("/detailed"):
        return "salesman_detailed"
    if request.GET.get("tab") == "reports":
        return "reports_home"
    return ""


def build_hub_nav(request):
    section = resolve_hub_section(request)
    subsection = resolve_hub_subsection(request)
    q = _q(request)

    main_tabs = [
        {
            "id": "overview",
            "label": "Overview",
            "icon": "fa-chart-line",
            "url": _home_url(request),
            "active": section == "overview",
        },
        {
            "id": "reports",
            "label": "Summary",
            "icon": "fa-clipboard-list",
            "url": _home_url(request, "reports"),
            "active": section == "reports",
        },
        {
            "id": "receivables",
            "label": "Receivables",
            "icon": "fa-hand-holding-dollar",
            "url": reverse("reporting:ar_aging") + q,
            "active": section == "receivables",
        },
        {
            "id": "payables",
            "label": "Payables",
            "icon": "fa-file-invoice-dollar",
            "url": reverse("reporting:ap_aging") + q,
            "active": section == "payables",
        },
        {
            "id": "cash",
            "label": "Cash & expenses",
            "icon": "fa-wallet",
            "url": reverse("reporting:cash_movement") + q,
            "active": section == "cash",
        },
        {
            "id": "trial",
            "label": "Trial balance",
            "icon": "fa-scale-balanced",
            "url": reverse("reporting:activity_trial_balance") + q,
            "active": section == "trial",
        },
        {
            "id": "salesman",
            "label": "Salesman",
            "icon": "fa-user-tie",
            "url": reverse("reporting:salesman_reports_home") + q,
            "active": section == "salesman",
        },
    ]

    sub_tabs = []
    if section == "receivables":
        sub_tabs = [
            {"id": "ar_aging", "label": "AR aging", "url": reverse("reporting:ar_aging") + q, "active": subsection == "ar_aging"},
            {"id": "all_clients", "label": "All clients SOA", "url": reverse("reporting:all_clients_statement") + q, "active": subsection == "all_clients"},
            {"id": "clients", "label": "Client list", "url": "/clients/", "active": False},
        ]
    elif section == "payables":
        sub_tabs = [
            {"id": "ap_aging", "label": "AP aging", "url": reverse("reporting:ap_aging") + q, "active": subsection == "ap_aging"},
            {"id": "all_suppliers", "label": "All suppliers SOA", "url": reverse("reporting:all_suppliers_statement") + q, "active": subsection == "all_suppliers"},
            {"id": "suppliers", "label": "Supplier list", "url": "/suppliers/", "active": False},
        ]
    elif section == "cash":
        sub_tabs = [
            {"id": "cash", "label": "Cash movement", "url": reverse("reporting:cash_movement") + q, "active": subsection == "cash"},
            {"id": "opex", "label": "OPEX by category", "url": reverse("reporting:opex_by_category") + q, "active": subsection == "opex"},
            {"id": "expenses", "label": "Operating expenses", "url": reverse("expenses:expense_list"), "active": False},
            {"id": "expense_new", "label": "+ New expense", "url": reverse("expenses:expense_create"), "active": False},
        ]
    elif section == "trial":
        sub_tabs = [
            {"id": "activity_tb", "label": "Activity / P&L", "url": reverse("reporting:activity_trial_balance") + q, "active": subsection == "activity_tb"},
            {"id": "clients_tb", "label": "Clients TB", "url": reverse("reporting:clients_trial_balance") + q, "active": subsection == "clients_tb"},
            {"id": "suppliers_tb", "label": "Suppliers TB", "url": reverse("reporting:suppliers_trial_balance") + q, "active": subsection == "suppliers_tb"},
        ]

    return {
        "hub_section": section,
        "hub_subsection": subsection,
        "hub_main_tabs": main_tabs,
        "hub_sub_tabs": sub_tabs,
    }
