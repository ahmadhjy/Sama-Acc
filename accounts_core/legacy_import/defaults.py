"""Shared defaults for legacy data imports."""

from accounts_core.models import Client, Employee, Supplier
from catalog.models import Destination, ServiceType
from treasury.models import MoneyAccount

LEGACY_SERVICE_CODE = "LEG-IMPORT"
LEGACY_DEST_NAME = "Legacy import"
LEGACY_SUPPLIER_CODE = "S-LEG-IMPORT"
LEGACY_MONEY_ACCOUNT = "Legacy import USD"


def get_legacy_import_context():
    """Return service type, destination, supplier, employee, money account for legacy rows."""
    service_type, _ = ServiceType.objects.get_or_create(
        code=LEGACY_SERVICE_CODE,
        defaults={
            "name": "Legacy import",
            "is_active": True,
            "requires_supplier": False,
            "default_currency": "USD",
        },
    )
    destination, _ = Destination.objects.get_or_create(
        name=LEGACY_DEST_NAME,
        defaults={"country": "", "is_active": True, "sort_order": 9999},
    )
    supplier, _ = Supplier.objects.get_or_create(
        supplier_code=LEGACY_SUPPLIER_CODE,
        defaults={
            "name": "Legacy import placeholder",
            "type": Supplier.SupplierType.OTHER,
            "default_currency": "USD",
            "managing_number": "LEG",
        },
    )
    employee = Employee.objects.filter(is_active=True).order_by("name").first()
    if not employee:
        raise RuntimeError("No active employee found — create at least one employee before importing legacy data.")
    money_account, _ = MoneyAccount.objects.get_or_create(
        name=LEGACY_MONEY_ACCOUNT,
        defaults={"type": MoneyAccount.AccountType.CASH, "currency": "USD", "is_active": True},
    )
    return {
        "service_type": service_type,
        "destination": destination,
        "supplier": supplier,
        "employee": employee,
        "money_account": money_account,
    }


def find_client_by_legacy_account(legacy_account: str):
    from accounts_core.legacy_import.client_pdf import legacy_client_code

    code = legacy_client_code(legacy_account)
    client = Client.objects.filter(client_code=code).first()
    if client:
        return client
    return Client.objects.filter(notes__contains=legacy_account).first()
