"""Suggest next client/supplier codes for create forms and quick-create APIs."""


def next_client_code():
    max_n = 0
    from accounts_core.models import Client

    for code in Client.objects.values_list("client_code", flat=True):
        if code.startswith("C-") and len(code) > 2 and code[2:].isdigit():
            max_n = max(max_n, int(code[2:]))
    return f"C-{max_n + 1:04d}"


def next_supplier_code():
    max_n = 0
    from accounts_core.models import Supplier

    for code in Supplier.objects.values_list("supplier_code", flat=True):
        if code.startswith("S-") and len(code) > 2 and code[2:].isdigit():
            max_n = max(max_n, int(code[2:]))
    return f"S-{max_n + 1:04d}"
