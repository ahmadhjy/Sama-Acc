"""Verify supplier ledger staging and Django balances match legacy PDF trial balance."""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django

django.setup()

from accounts_core.models import Supplier
from reporting.balances import supplier_ap_balance

PDF_BALANCES = {
    "4010000004": Decimal("4564.97"),
    "4010000007": Decimal("9978.60"),
    "4010000008": Decimal("-34.79"),
    "4010000009": Decimal("0.75"),
    "4010000012": Decimal("92.66"),
    "4010000013": Decimal("736.00"),
    "4010000014": Decimal("8260.07"),
    "4010000016": Decimal("3748.13"),
    "4010000017": Decimal("805.00"),
    "4010000020": Decimal("28.02"),
    "4010000025": Decimal("164.00"),
    "4010000028": Decimal("6216.00"),
    "4010000030": Decimal("121.59"),
    "4010000031": Decimal("2470.00"),
    "4010000032": Decimal("71.00"),
    "4010000033": Decimal("12616.13"),
    "4010000035": Decimal("1879.53"),
    "4010000038": Decimal("-2592.84"),
    "4010000054": Decimal("0.59"),
    "4010000056": Decimal("80.00"),
    "4010000063": Decimal("179.64"),
    "4010000067": Decimal("7.40"),
    "4010000082": Decimal("360.00"),
    "4010000084": Decimal("-68.00"),
    "4010000091": Decimal("364.00"),
    "4010000094": Decimal("7218.82"),
}

DATE_FROM = date(2026, 1, 1)
DATE_TO = date(2026, 12, 31)


def staging_balances(staging_dir: Path) -> dict[str, Decimal]:
    credits = defaultdict(Decimal)
    debits = defaultdict(Decimal)
    path = staging_dir / "supplier_ledger_lines.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if not (DATE_FROM.isoformat() <= row["line_date"] <= DATE_TO.isoformat()):
            continue
        acc = row["legacy_accno"]
        amt = Decimal(row["amount"])
        if row["dc"] == "C":
            credits[acc] += amt
        else:
            debits[acc] += amt
    balances = {}
    for acc in set(credits) | set(debits):
        balances[acc] = credits[acc] - debits[acc]
    return balances


def main():
    staging_dir = PROJECT_ROOT / "exports" / "sato26" / "staging"
    staging = staging_balances(staging_dir)

    print("=== STAGING ledger vs PDF ===")
    staging_mismatch = 0
    for acc, pdf_bal in sorted(PDF_BALANCES.items()):
        st = staging.get(acc, Decimal("0"))
        if abs(st - pdf_bal) > Decimal("0.02"):
            staging_mismatch += 1
            print(f"MISMATCH {acc}: pdf={pdf_bal} staging={st} diff={st-pdf_bal}")
    print(f"Staging parity: {len(PDF_BALANCES) - staging_mismatch}/{len(PDF_BALANCES)}")

    as_of = DATE_TO
    print("\n=== DJANGO vs PDF ===")
    django_mismatch = 0
    for acc, pdf_bal in sorted(PDF_BALANCES.items()):
        supplier = Supplier.objects.filter(supplier_code=f"S-{acc}").first()
        if not supplier:
            django_mismatch += 1
            print(f"MISSING supplier S-{acc}")
            continue
        dj = supplier_ap_balance(supplier, as_of)
        if abs(dj - pdf_bal) > Decimal("0.02"):
            django_mismatch += 1
            print(f"MISMATCH {acc}: pdf={pdf_bal} django={dj} diff={dj-pdf_bal}")
    print(f"Django parity: {len(PDF_BALANCES) - django_mismatch}/{len(PDF_BALANCES)}")


if __name__ == "__main__":
    main()
