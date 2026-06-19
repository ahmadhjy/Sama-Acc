"""Parse client Statement-of-Account PDFs from the legacy ERP."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from accounts_core.legacy_import.client_pdf import LEGACY_ACCOUNT_RE, load_pdf_text, parse_soa_account_block

SOA_DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
SOA_JV_RE = re.compile(r"^\d+$")
SOA_AMOUNT_RE = re.compile(r"^-?\d[\d,]*\.\d+$")


@dataclass
class LegacySoaTransaction:
    jv_no: str
    trans_date: datetime.date
    description: str
    debit: Decimal
    credit: Decimal
    balance: Decimal
    legacy_account: str = ""
    client_name: str = ""
    source_file: str = ""

    @property
    def is_payment(self) -> bool:
        if self.credit > 0:
            return True
        if self.debit < 0:
            return True
        desc = self.description.upper()
        if "RECEIPT VOUCHER" in desc or "RECEIPT VOUCHER-" in desc:
            return True
        return False

    @property
    def payment_amount(self) -> Decimal:
        if self.credit > 0:
            return self.credit
        if self.debit < 0:
            return abs(self.debit)
        return Decimal("0")

    @property
    def invoice_amount(self) -> Decimal:
        if self.debit > 0:
            return self.debit
        if self.credit < 0:
            return abs(self.credit)
        return Decimal("0")


def _parse_amount(raw: str) -> Decimal:
    return Decimal(raw.strip().replace(",", ""))


def parse_soa_transactions(text: str) -> list[LegacySoaTransaction]:
    """
    Parse transaction rows from legacy client SOA PDF text.

    Pattern: JV#, date, description, debit, credit, balance
    Detail lines with 0 debit and 0 credit are skipped.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    start = 0
    for idx, ln in enumerate(lines):
        if ln == "Tel :" or ln.startswith("Tel :"):
            start = idx + 1
            break

    rows: list[LegacySoaTransaction] = []
    i = start
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("Page ") or ln == "Totals :":
            break
        if not SOA_JV_RE.match(ln):
            i += 1
            continue
        jv = ln
        i += 1
        if i >= len(lines) or not SOA_DATE_RE.match(lines[i]):
            continue
        trans_date = datetime.strptime(lines[i], "%d/%m/%Y").date()
        i += 1

        desc_parts: list[str] = []
        while i < len(lines):
            candidate = lines[i].strip()
            if SOA_JV_RE.match(candidate) and i + 1 < len(lines) and SOA_DATE_RE.match(lines[i + 1]):
                break
            cleaned = candidate.replace(",", "")
            if SOA_AMOUNT_RE.match(cleaned):
                break
            if candidate == "USD":
                break
            desc_parts.append(lines[i])
            i += 1

        amounts: list[Decimal] = []
        while i < len(lines) and len(amounts) < 3:
            candidate = lines[i].strip().replace(",", "")
            if SOA_AMOUNT_RE.match(candidate):
                amounts.append(_parse_amount(candidate))
                i += 1
            else:
                break

        if len(amounts) < 3:
            continue

        debit, credit, balance = amounts[0], amounts[1], amounts[2]
        desc = " ".join(p for p in desc_parts if p and p != "-").strip()
        if debit == 0 and credit == 0:
            continue

        rows.append(
            LegacySoaTransaction(
                jv_no=jv,
                trans_date=trans_date,
                description=desc or f"Legacy JV#{jv}",
                debit=debit,
                credit=credit,
                balance=balance,
            )
        )
    return rows


def load_soa_pdf(path: Path) -> tuple[str, str, list[LegacySoaTransaction]]:
    """Load one client SOA PDF; return (legacy_account, client_name, transactions)."""
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF (fitz) is required to read legacy PDF files.") from exc

    doc = fitz.open(path)
    try:
        text = "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()

    name_raw, legacy_account, _, _ = parse_soa_account_block(text)
    if not legacy_account:
        raise ValueError(f"Could not find legacy account in {path.name}")

    txs = parse_soa_transactions(text)
    for tx in txs:
        tx.legacy_account = legacy_account
        tx.client_name = name_raw
        tx.source_file = path.name
    return legacy_account, name_raw, txs


def discover_client_soa_files(clients_dir: Path) -> list[Path]:
    if not clients_dir.is_dir():
        raise FileNotFoundError(f"Clients folder not found: {clients_dir}")
    paths = []
    for path in sorted(clients_dir.glob("*.pdf")):
        upper = path.name.upper()
        if upper.startswith("CLIENTS STATEMENT"):
            continue
        paths.append(path)
    return paths
