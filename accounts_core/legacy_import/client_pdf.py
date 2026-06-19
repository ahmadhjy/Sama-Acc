"""Parse client master data from legacy ERP PDF exports."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

LEGACY_ACCOUNT_RE = re.compile(r"^411\d{7}$")
NAME_SUFFIX_RE = re.compile(r"\s*\(\d+\)\s*$")
AMOUNT_RE = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")

CORPORATE_HINTS = (
    "CLIENTS BEFORE REQUEST",
    "SAMA SANDOUK",
    "SAMA PEG",
    "SANDOUK IN",
)


@dataclass
class LegacyClientRow:
    name_raw: str
    legacy_account: str
    currency: str = "USD"
    balance_debit: Decimal = Decimal("0")
    balance_credit: Decimal = Decimal("0")
    total_debit: Decimal = Decimal("0")
    total_credit: Decimal = Decimal("0")
    address: str = ""
    phone: str = ""
    source_file: str = ""

    @property
    def name_en(self) -> str:
        cleaned = NAME_SUFFIX_RE.sub("", self.name_raw.strip())
        return cleaned.title()

    @property
    def client_type(self) -> str:
        upper = self.name_raw.upper()
        if any(h in upper for h in CORPORATE_HINTS):
            return "CORPORATE"
        return "INDIVIDUAL"

    @property
    def closing_balance(self) -> Decimal:
        return self.balance_debit - self.balance_credit


def _parse_amount(raw: str) -> Decimal:
    text = (raw or "").strip().replace(",", "")
    if not text:
        return Decimal("0")
    return Decimal(text)


def parse_trial_balance_text(text: str, source_file: str = "") -> list[LegacyClientRow]:
    """
    Parse the legacy 'Trial Balance' PDF text (CLIENTS STATEMENT TILL *.pdf).

    Row pattern: NAME, USD, balance_dr, balance_cr, total_dr, total_cr, 411xxxxxxxx
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    rows: list[LegacyClientRow] = []
    skip_names = {
        "Name",
        "Curr",
        "USD",
        "Trial Balance",
        "Debit",
        "Credit",
        "Balance",
        "Totals :",
    }

    i = 0
    while i < len(lines):
        if lines[i] != "USD":
            i += 1
            continue
        if i == 0:
            i += 1
            continue
        name = lines[i - 1]
        if name in skip_names or name.startswith("From Account") or name.startswith("Till Account"):
            i += 1
            continue
        if i + 5 >= len(lines):
            break
        amounts = lines[i + 1 : i + 5]
        account = lines[i + 5]
        if not LEGACY_ACCOUNT_RE.match(account):
            i += 1
            continue
        if not all(AMOUNT_RE.match(a) for a in amounts):
            i += 1
            continue
        rows.append(
            LegacyClientRow(
                name_raw=name,
                legacy_account=account,
                currency="USD",
                balance_debit=_parse_amount(amounts[0]),
                balance_credit=_parse_amount(amounts[1]),
                total_debit=_parse_amount(amounts[2]),
                total_credit=_parse_amount(amounts[3]),
                source_file=source_file,
            )
        )
        i += 6
    return rows


def parse_soa_account_block(text: str) -> tuple[str, str, str, str]:
    """
    Extract (name_raw, legacy_account, address, phone) from an individual SOA PDF.
    Address/phone are usually empty in these exports.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    name_raw = ""
    legacy_account = ""
    address = ""
    phone = ""

    for idx, line in enumerate(lines):
        if LEGACY_ACCOUNT_RE.match(line):
            legacy_account = line
            if idx >= 2 and lines[idx - 1] == "USD":
                candidate = lines[idx - 2]
                if candidate not in {"Balance", "Description", "Credit", "Debit", "To :", "Account :"}:
                    name_raw = candidate
            break

    if "Address" in lines:
        addr_idx = lines.index("Address")
        if addr_idx + 1 < len(lines) and lines[addr_idx + 1] != "Tel":
            maybe = lines[addr_idx + 1]
            if maybe and maybe != "Tel :" and not maybe.startswith("Tel"):
                if maybe.isdigit() and len(maybe) <= 4:
                    pass
                elif sum(ch.isdigit() for ch in maybe) >= 7:
                    phone = maybe
                else:
                    address = maybe

    for idx, line in enumerate(lines):
        if line.startswith("Tel :") or line == "Tel :":
            if idx + 1 < len(lines):
                val = lines[idx + 1]
                if val and not val.isdigit():
                    phone = val
                elif val and len(val) >= 7:
                    phone = val

    return name_raw, legacy_account, address, phone


def load_pdf_text(path: Path) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF (fitz) is required to read legacy PDF files.") from exc
    doc = fitz.open(path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def discover_client_rows(clients_dir: Path) -> list[LegacyClientRow]:
    """
    Build client list from trial balance PDF, enriched by individual SOA PDFs.
    """
    if not clients_dir.is_dir():
        raise FileNotFoundError(f"Clients folder not found: {clients_dir}")

    summary_pdf = None
    for path in clients_dir.glob("*.pdf"):
        if path.name.upper().startswith("CLIENTS STATEMENT"):
            summary_pdf = path
            break
    if not summary_pdf:
        raise FileNotFoundError(
            f"No summary trial balance PDF found in {clients_dir} (expected 'CLIENTS STATEMENT*.pdf')."
        )

    rows = parse_trial_balance_text(load_pdf_text(summary_pdf), source_file=summary_pdf.name)
    by_account = {r.legacy_account: r for r in rows}

    for path in sorted(clients_dir.glob("*.pdf")):
        if path == summary_pdf or "Before Request" in path.name:
            continue
        text = load_pdf_text(path)
        name_raw, account, address, phone = parse_soa_account_block(text)
        if not account:
            continue
        row = by_account.get(account)
        if row is None:
            row = LegacyClientRow(name_raw=name_raw or path.stem, legacy_account=account, source_file=path.name)
            rows.append(row)
            by_account[account] = row
        if address and not row.address:
            row.address = address
        if phone and len(phone) >= 7 and not row.phone:
            row.phone = phone

    rows.sort(key=lambda r: r.legacy_account)
    return rows


def legacy_client_code(legacy_account: str) -> str:
    """Map 4110000505 -> C-0505 (last 4 digits of legacy account)."""
    suffix = legacy_account[-4:]
    return f"C-{suffix}"


def build_import_notes(row: LegacyClientRow) -> str:
    parts = [
        "Imported from legacy ERP PDF export.",
        f"Legacy account: {row.legacy_account}",
        f"Balance debit: {row.balance_debit} {row.currency}",
        f"Balance credit: {row.balance_credit} {row.currency}",
        f"Total debit: {row.total_debit} | Total credit: {row.total_credit}",
        f"Closing balance: {row.closing_balance} {row.currency}",
    ]
    if row.source_file:
        parts.append(f"Source: {row.source_file}")
    return "\n".join(parts)
