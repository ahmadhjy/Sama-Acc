"""
Extract SATO26 legacy data into Sama Accounting staging JSON.

Reads from restored SQL Server database SATO26_RESTORE (or CSV fallback).

Usage:
    python migration/sato26/extract_staging.py
    python migration/sato26/extract_staging.py --output exports/sato26/staging
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV_DIR = PROJECT_ROOT / "exports" / "sato26"
DEFAULT_OUTPUT = PROJECT_ROOT / "exports" / "sato26" / "staging"

try:
    from migration.sato26.legacy_parse import (
        ITEM_LABELS,
        package_type_for_item,
    )
except ModuleNotFoundError:
    from legacy_parse import (
        ITEM_LABELS,
        package_type_for_item,
    )

LEGACY_CURRENCY_MAP = {
    "1": "USD",
    "2": "USD",  # SATO26 travel invoices: amounts are USD; Curr=2 is local chart setting
}


def D(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def parse_date(value) -> date | None:
    if value is None or str(value).strip() in ("", "NULL"):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%m/%d/%Y %I:%M:%S %p",
        "%d/%m/%Y %I:%M:%S %p",
        "%m/%d/%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def clean_phone(*parts) -> str:
    for p in parts:
        p = (p or "").strip()
        if p:
            return p
    return ""


def connect_sql():
    import pyodbc

    drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
    preferred = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server",
    ]
    driver = next((d for d in preferred if d in drivers), drivers[0] if drivers else None)
    if not driver:
        raise RuntimeError("No SQL Server ODBC driver installed")
    conn_str = (
        f"DRIVER={{{driver}}};SERVER=localhost;DATABASE=SATO26_RESTORE;"
        "Trusted_Connection=yes;TrustServerCertificate=yes;Encrypt=yes;"
    )
    return pyodbc.connect(conn_str)


def fetch_all(conn, sql: str) -> list[dict]:
    cur = conn.cursor()
    cur.execute(sql)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def read_csv(name: str, csv_dir: Path) -> list[dict]:
    path = csv_dir / f"{name}.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_source(csv_dir: Path):
    try:
        conn = connect_sql()
        idcards = fetch_all(conn, "SELECT * FROM dbo.IDCard")
        headers = fetch_all(conn, "SELECT * FROM dbo.SalesHeader WHERE Type='SI'")
        footers = fetch_all(conn, "SELECT * FROM dbo.SalesFooter WHERE Type='SI'")
        accounts = fetch_all(conn, "SELECT * FROM dbo.Accounts")
        jheaders = fetch_all(conn, "SELECT * FROM dbo.JournalHeader")
        jdetails = fetch_all(conn, "SELECT * FROM dbo.JournalDetail")
        unpaid = fetch_all(conn, "SELECT * FROM dbo.UnpaidInvoices")
        company = fetch_all(conn, "SELECT TOP 1 * FROM dbo.Company")
        conn.close()
        return {
            "source": "sql",
            "idcards": idcards,
            "headers": headers,
            "footers": footers,
            "accounts": accounts,
            "jheaders": jheaders,
            "jdetails": jdetails,
            "unpaid": unpaid,
            "company": company[0] if company else {},
        }
    except Exception as exc:
        print(f"SQL unavailable ({exc}), using CSV fallback")
        return {
            "source": "csv",
            "idcards": read_csv("IDCard", csv_dir),
            "headers": [r for r in read_csv("SalesHeader", csv_dir) if r.get("Type") == "SI"],
            "footers": [r for r in read_csv("SalesFooter", csv_dir) if r.get("Type") == "SI"],
            "accounts": read_csv("Accounts", csv_dir),
            "jheaders": read_csv("JournalHeader", csv_dir),
            "jdetails": read_csv("JournalDetail", csv_dir),
            "unpaid": read_csv("UnpaidInvoices", csv_dir),
            "company": (read_csv("Company", csv_dir) or [{}])[0],
        }


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def build_account_lookup(accounts: list[dict]) -> dict[str, dict]:
    return {str(a.get("AccNo") or "").strip(): a for a in accounts if a.get("AccNo")}


def _gl_account_display_name(acc: dict) -> str:
    return (acc.get("AccName1") or acc.get("AccName2") or "").strip()


def _client_gl_accounts_by_idno(accounts: list[dict]) -> dict[str, dict]:
    """Map legacy client IDNO -> primary 411 GL account (name + number)."""
    by_idno: dict[str, dict] = {}
    for acc in accounts:
        acc_no = str(acc.get("AccNo") or "").strip()
        if not acc_no.startswith("411"):
            continue
        idno = str(acc.get("IDNO") or "").strip()
        if not idno:
            continue
        name = _gl_account_display_name(acc)
        existing = by_idno.get(idno)
        if not existing or len(acc_no) >= len(existing.get("acc_no", "")):
            by_idno[idno] = {"acc_no": acc_no, "name": name}
    return by_idno


def transform_clients(idcards: list[dict], accounts: list[dict] | None = None) -> list[dict]:
    gl_by_idno = _client_gl_accounts_by_idno(accounts or [])
    clients = []
    seen = set()
    for row in idcards:
        if str(row.get("Type") or "").upper() != "C":
            continue
        legacy_id = str(row.get("IDNO") or "").strip()
        if not legacy_id or legacy_id in seen:
            continue
        seen.add(legacy_id)
        idcard_name = (row.get("AccName") or "").strip()
        gl = gl_by_idno.get(legacy_id, {})
        gl_name = (gl.get("name") or "").strip()
        gl_acc = (gl.get("acc_no") or "").strip()
        name = gl_name if gl_name else (idcard_name or f"Client {legacy_id}")
        acc_no = gl_acc or (row.get("AccNo") or "").strip()
        notes_parts = []
        if (row.get("Remark") or "").strip():
            notes_parts.append((row.get("Remark") or "").strip())
        if idcard_name and gl_name and idcard_name.upper() != gl_name.upper():
            notes_parts.append(f"Legacy IDCard name: {idcard_name}")
        code = f"C-{legacy_id}"
        clients.append(
            {
                "legacy_id": legacy_id,
                "legacy_acc_no": acc_no,
                "legacy_gl_account": gl_acc,
                "client_code": code,
                "name_en": name,
                "type": "CORPORATE" if str(row.get("Official") or "").upper() == "Y" else "INDIVIDUAL",
                "phone": clean_phone(row.get("Mobile"), row.get("Tel1"), row.get("Tel2")),
                "email": (row.get("Email") or "").strip(),
                "address": " ".join(
                    p for p in [(row.get("Address1") or ""), (row.get("Address2") or ""), (row.get("Address3") or "")]
                    if p and str(p).strip()
                ).strip(),
                "notes": "\n".join(notes_parts),
                "legacy_route": str(row.get("Route") or "").strip(),
                "date_of_birth": parse_date(row.get("BirthDay")).isoformat() if parse_date(row.get("BirthDay")) else None,
            }
        )

    for legacy_id, gl in sorted(gl_by_idno.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0]):
        if legacy_id in seen:
            continue
        seen.add(legacy_id)
        gl_name = (gl.get("name") or "").strip() or f"Client {legacy_id}"
        gl_acc = (gl.get("acc_no") or "").strip()
        clients.append(
            {
                "legacy_id": legacy_id,
                "legacy_acc_no": gl_acc,
                "legacy_gl_account": gl_acc,
                "client_code": f"C-{legacy_id}",
                "name_en": gl_name,
                "type": "INDIVIDUAL",
                "phone": "",
                "email": "",
                "address": "",
                "notes": "Imported from legacy GL account only (no IDCard row).",
                "legacy_route": "",
                "date_of_birth": None,
            }
        )
    return sorted(clients, key=lambda c: c["client_code"])


def transform_employees(idcards: list[dict]) -> list[dict]:
    """Type A IDCard rows are legacy sales agents."""
    employees = []
    for row in idcards:
        if str(row.get("Type") or "").upper() != "A":
            continue
        legacy_id = str(row.get("IDNO") or "").strip()
        if not legacy_id:
            continue
        name = (row.get("AccName") or "").strip() or f"Agent {legacy_id}"
        employees.append(
            {
                "legacy_id": legacy_id,
                "employee_code": f"E-{legacy_id}",
                "name": name,
                "legacy_route": str(row.get("Route") or "").strip(),
                "role": "SALES",
            }
        )
    return sorted(employees, key=lambda e: int(e["legacy_id"]) if e["legacy_id"].isdigit() else e["legacy_id"])


def build_employee_route_index(employees: list[dict]) -> tuple[dict[str, str], str | None]:
    """Route code → employee_code; fallback for clients with no route."""
    by_route: dict[str, str] = {}
    fallback: str | None = None
    for emp in employees:
        route = emp.get("legacy_route") or ""
        if route and route not in by_route:
            by_route[route] = emp["employee_code"]
    for emp in employees:
        if not (emp.get("legacy_route") or ""):
            fallback = emp["employee_code"]
            break
    if not fallback and employees:
        fallback = employees[0]["employee_code"]
    return by_route, fallback


def resolve_sales_employee_code(
    client: dict,
    employees_by_route: dict[str, str],
    fallback_code: str | None,
) -> str | None:
    route = client.get("legacy_route") or ""
    if route and route in employees_by_route:
        return employees_by_route[route]
    return fallback_code


def transform_suppliers(accounts: list[dict], footers: list[dict]) -> list[dict]:
    used_codes = {str(f.get("CodeMain") or "").strip() for f in footers if f.get("CodeMain")}
    suppliers = []
    seen = set()
    for acc in accounts:
        acc_no = str(acc.get("AccNo") or "").strip()
        if not acc_no.startswith("401") and acc_no not in used_codes:
            continue
        if acc_no in seen:
            continue
        seen.add(acc_no)
        name = _gl_account_display_name(acc) or f"Supplier {acc_no}"
        suppliers.append(
            {
                "legacy_acc_no": acc_no,
                "legacy_gl_account": acc_no,
                "supplier_code": f"S-{acc_no}"[:32],
                "name": name,
                "type": "OTHER",
                "phone": clean_phone(acc.get("Cellular"), acc.get("Tel")),
                "email": (acc.get("Email") or "").strip(),
                "address": " ".join(p for p in [acc.get("Address1"), acc.get("Address2")] if p and str(p).strip()).strip(),
                "default_currency": LEGACY_CURRENCY_MAP.get(str(acc.get("Curr") or "1"), "USD"),
            }
        )
    return sorted(suppliers, key=lambda s: s["supplier_code"])


def transform_service_types(footers: list[dict]) -> list[dict]:
    codes = sorted({str(f.get("ItemCode") or "").strip() for f in footers if f.get("ItemCode")})
    types = []
    for code in codes:
        label = ITEM_LABELS.get(code, f"Service {code}")
        types.append(
            {
                "legacy_item_code": code,
                "code": f"LEG-{code}",
                "name": label,
                "requires_supplier": True,
                "default_currency": "USD",
            }
        )
    return types


def transform_invoices(
    headers: list[dict],
    footers: list[dict],
    clients_by_legacy: dict[str, dict],
    suppliers_by_acc: dict[str, dict],
    service_by_item: dict[str, dict],
) -> list[dict]:
    lines_by_inv = defaultdict(list)
    for f in footers:
        key = str(f.get("InvNumber") or "").strip()
        lines_by_inv[key].append(f)

    invoices = []
    for h in headers:
        inv_no = str(h.get("InvNumber") or "").strip()
        legacy_client_id = str(h.get("DBAccount") or "").strip()
        client = clients_by_legacy.get(legacy_client_id)
        if not client:
            continue
        curr = LEGACY_CURRENCY_MAP.get(str(h.get("Curr") or "2"), "USD")
        rate = D(h.get("Rate"))
        if curr == "USD":
            fx = Decimal("1")
        elif rate > 0:
            fx = (Decimal("1") / rate).quantize(Decimal("0.000001"))
        else:
            fx = Decimal("1")

        primary_item_code = ""
        line_rows = []

        for f in sorted(lines_by_inv.get(inv_no, []), key=lambda x: int(D(x.get("Recno") or 0))):
            item_code = str(f.get("ItemCode") or "").strip()
            if not primary_item_code and item_code:
                primary_item_code = item_code
            st = service_by_item.get(item_code, {})
            sup_acc = str(f.get("CodeMain") or "").strip()
            sup = suppliers_by_acc.get(sup_acc)
            qty = D(f.get("Qty")) or Decimal("1")
            sell = D(f.get("Price"))
            cost = D(f.get("AvCost"))
            legacy_note = (f.get("Note") or "").strip()
            line_rows.append(
                {
                    "legacy_recno": str(f.get("Recno") or ""),
                    "service_type_code": st.get("code", f"LEG-{item_code or 'GEN'}"),
                    "supplier_code": sup.get("supplier_code") if sup else None,
                    "supplier_legacy_acc": sup_acc or None,
                    "qty": str(qty),
                    "sell_price": str(sell),
                    "cost_price": str(cost),
                    "line_discount": "0",
                    "service_date": (
                        parse_date(f.get("DateInvoice")) or parse_date(h.get("Date")) or date.today()
                    ).isoformat(),
                    "line_notes": legacy_note[:255],
                    "line_data": {
                        "legacy_item_code": item_code,
                        "legacy_note": legacy_note,
                        "description": legacy_note or st.get("name", "Service"),
                    },
                    "description": legacy_note or st.get("name", "Service"),
                }
            )

        if not line_rows:
            continue

        header_note = (h.get("Note") or "").strip()
        header_ref = (h.get("REF") or "").strip()
        internal_note = " | ".join(p for p in [header_note, f"REF: {header_ref}" if header_ref else ""] if p)

        invoices.append(
            {
                "legacy_inv_number": inv_no,
                "invoice_no": f"SATO26-SI-{inv_no.zfill(5)}",
                "client_code": client["client_code"],
                "legacy_client_id": legacy_client_id,
                "package_type": package_type_for_item(primary_item_code),
                "issue_date": (parse_date(h.get("Date")) or date.today()).isoformat(),
                "due_date": (parse_date(h.get("Maturity")) or parse_date(h.get("Date")) or date.today()).isoformat(),
                "currency": curr,
                "exchange_rate_to_usd": str(fx),
                "status": "POSTED",
                "legacy_jvno": str(h.get("JVNO") or ""),
                "legacy_ref": header_ref,
                "note": internal_note,
                "amount_paid_legacy": str(D(h.get("AmountPaid"))),
                "amount_rest_legacy": str(D(h.get("AmountRest"))),
                "lines": line_rows,
            }
        )
    return invoices


def _parse_client_acc_from_note(note: str) -> str | None:
    m = re.search(r"411\d+", note or "")
    return m.group(0) if m else None


def _resolve_client(clients_by_acc: dict[str, dict], acc_no: str, note: str = "") -> dict | None:
    acc = str(acc_no or "").strip()
    if not acc:
        return None
    for key in (acc, acc.lstrip("0")):
        if key in clients_by_acc:
            return clients_by_acc[key]
    guess = _parse_client_acc_from_note(note)
    if guess and guess in clients_by_acc:
        return clients_by_acc[guess]
    return None


def _resolve_supplier(suppliers_by_acc: dict[str, dict], acc_no: str) -> dict | None:
    acc = str(acc_no or "").strip()
    if not acc:
        return None
    for key in (acc, acc.lstrip("0")):
        if key in suppliers_by_acc:
            return suppliers_by_acc[key]
    return None


def _payment_receipt_no(typ: str, jvno: str, acc_no: str, seq: int) -> str:
    base = f"SATO26-{typ}-{jvno.zfill(5)}"
    if seq == 0:
        return base
    tail = re.sub(r"\D", "", acc_no or "")[-4:] or str(seq)
    return f"{base}-{tail}"


def transform_payments(
    jheaders: list[dict],
    jdetails: list[dict],
    clients_by_acc: dict[str, dict],
    suppliers_by_acc: dict[str, dict],
    invoices_by_client: dict[str, list[dict]],
) -> list[dict]:
    """Map every legacy RV/PV line on 411 (client) or 401 (supplier) to a treasury payment."""
    details_by_jv = defaultdict(list)
    for d in jdetails:
        key = (str(d.get("Type") or ""), str(d.get("JVNO") or ""))
        details_by_jv[key].append(d)

    payments = []
    for h in jheaders:
        typ = str(h.get("Type") or "").upper()
        if typ not in ("RV", "PV"):
            continue
        jvno = str(h.get("JVNO") or "")
        rows = details_by_jv.get((typ, jvno), [])
        if not rows:
            continue
        pay_date = parse_date(h.get("Date")) or date.today()
        header_note = (h.get("Note") or "").strip()
        ref = (h.get("REF") or "").strip()

        client_lines = [r for r in rows if str(r.get("ACCNO") or "").startswith("411")]
        supplier_lines = [r for r in rows if str(r.get("ACCNO") or "").startswith("401")]

        ci = 0
        for row in client_lines:
            amt = D(row.get("AMT"))
            if amt <= 0:
                continue
            dc = str(row.get("DC") or "").upper()
            line_note = (row.get("Note") or header_note or "").strip()
            client = _resolve_client(clients_by_acc, str(row.get("ACCNO") or ""), line_note)
            if not client:
                continue
            if typ == "RV" and dc == "C":
                direction = "IN"
            elif typ == "PV" and dc == "D":
                direction = "OUT"
            elif typ == "RV" and dc == "D":
                direction = "OUT"
            elif typ == "PV" and dc == "C":
                direction = "IN"
            else:
                continue
            payments.append(
                {
                    "legacy_type": typ,
                    "legacy_jvno": jvno,
                    "legacy_accno": str(row.get("ACCNO") or ""),
                    "receipt_no": _payment_receipt_no(typ, jvno, str(row.get("ACCNO") or ""), ci),
                    "direction": direction,
                    "party_type": "CLIENT",
                    "client_code": client["client_code"],
                    "supplier_code": None,
                    "party_name": "",
                    "date": pay_date.isoformat(),
                    "currency": "USD",
                    "amount": str(amt),
                    "exchange_rate": "1",
                    "reference": ref,
                    "note": line_note,
                    "is_refund": direction == "OUT",
                    "status": "POSTED",
                }
            )
            ci += 1

        si = 0
        for row in supplier_lines:
            amt = D(row.get("AMT"))
            if amt <= 0:
                continue
            dc = str(row.get("DC") or "").upper()
            line_note = (row.get("Note") or header_note or "").strip()
            supplier = _resolve_supplier(suppliers_by_acc, str(row.get("ACCNO") or ""))
            if not supplier:
                continue
            if typ == "PV" and dc == "D":
                direction = "OUT"
            elif typ == "RV" and dc == "C":
                direction = "IN"
            elif typ == "PV" and dc == "C":
                direction = "IN"
            elif typ == "RV" and dc == "D":
                direction = "OUT"
            else:
                continue
            payments.append(
                {
                    "legacy_type": typ,
                    "legacy_jvno": jvno,
                    "legacy_accno": str(row.get("ACCNO") or ""),
                    "receipt_no": _payment_receipt_no(typ, jvno, str(row.get("ACCNO") or ""), si),
                    "direction": direction,
                    "party_type": "SUPPLIER",
                    "client_code": None,
                    "supplier_code": supplier["supplier_code"],
                    "party_name": "",
                    "date": pay_date.isoformat(),
                    "currency": "USD",
                    "amount": str(amt),
                    "exchange_rate": "1",
                    "reference": ref,
                    "note": line_note,
                    "is_refund": False,
                    "status": "POSTED",
                }
            )
            si += 1
    return payments


def _jvno_to_invoice_map(headers: list[dict]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for h in headers:
        if str(h.get("Type") or "").upper() != "SI":
            continue
        jvno = str(h.get("JVNO") or "").strip()
        inv = str(h.get("InvNumber") or "").strip()
        if jvno and inv:
            mapping[jvno] = inv
    return mapping


def transform_supplier_journal_credits(
    jheaders: list[dict],
    jdetails: list[dict],
    suppliers_by_acc: dict[str, dict],
    headers: list[dict],
) -> list[dict]:
    """Legacy SI journal credits on 401* accounts (supplier trial balance parity)."""
    details_by_jv = defaultdict(list)
    for d in jdetails:
        key = (str(d.get("Type") or ""), str(d.get("JVNO") or ""))
        details_by_jv[key].append(d)

    inv_by_jvno = _jvno_to_invoice_map(headers)
    credits = []
    for h in jheaders:
        typ = str(h.get("Type") or "").upper()
        if typ != "SI":
            continue
        jvno = str(h.get("JVNO") or "")
        credit_date = parse_date(h.get("Date")) or date.today()
        rows = details_by_jv.get((typ, jvno), [])
        seq = 0
        for row in rows:
            if str(row.get("DC") or "").upper() != "C":
                continue
            acc_no = str(row.get("ACCNO") or "")
            if not acc_no.startswith("401"):
                continue
            amt = D(row.get("AMT"))
            if amt <= 0:
                continue
            supplier = _resolve_supplier(suppliers_by_acc, acc_no)
            if not supplier:
                continue
            inv_num = inv_by_jvno.get(jvno, "")
            invoice_no = f"SATO26-SI-{inv_num.zfill(5)}" if inv_num else ""
            line_note = (row.get("Note") or "").strip()
            credits.append(
                {
                    "legacy_key": f"SATO26-SJC-{jvno.zfill(5)}-{acc_no}-{seq}",
                    "legacy_jvno": jvno,
                    "legacy_accno": acc_no,
                    "line_seq": seq,
                    "supplier_code": supplier["supplier_code"],
                    "credit_date": credit_date.isoformat(),
                    "amount": str(amt),
                    "invoice_no": invoice_no,
                    "description": line_note or (f"Purchase JV {jvno}" if not invoice_no else f"Invoice {invoice_no}"),
                }
            )
            seq += 1
    return credits


EXPENSE_ACCOUNT_PREFIXES = ("626", "631")


def build_expense_accounts_index(accounts: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for acc in accounts:
        acc_no = str(acc.get("AccNo") or "").strip()
        if not any(acc_no.startswith(prefix) for prefix in EXPENSE_ACCOUNT_PREFIXES):
            continue
        name = (acc.get("AccName1") or acc.get("AccName2") or "").strip() or f"Expense {acc_no}"
        index[acc_no] = {
            "code": acc_no[:20],
            "name": name[:100],
            "legacy_acc_no": acc_no,
        }
    return index


def _category_for_expense(acc_no: str, expense_accounts: dict[str, dict]) -> dict:
    acc = str(acc_no or "").strip()
    if acc in expense_accounts:
        return expense_accounts[acc]
    if acc.startswith("626"):
        return {"code": "626", "name": "General operating expenses"}
    if acc.startswith("631"):
        return {"code": "631", "name": "Marketing & administrative expenses"}
    return {"code": "OPEX", "name": "Operating expenses"}


def _opex_expense_no(jvno: str, acc_no: str, seq: int) -> str:
    base = f"SATO26-OPEX-{jvno.zfill(5)}"
    if seq == 0:
        return base
    tail = re.sub(r"\D", "", acc_no or "")[-4:] or str(seq)
    return f"{base}-{tail}"


def transform_operating_expenses(
    jheaders: list[dict],
    jdetails: list[dict],
    expense_accounts: dict[str, dict],
) -> list[dict]:
    """Legacy PV debit lines on 626/631 expense accounts → operating expenses."""
    details_by_jv = defaultdict(list)
    for d in jdetails:
        key = (str(d.get("Type") or ""), str(d.get("JVNO") or ""))
        details_by_jv[key].append(d)

    expenses = []
    for h in jheaders:
        typ = str(h.get("Type") or "").upper()
        if typ != "PV":
            continue
        jvno = str(h.get("JVNO") or "")
        rows = details_by_jv.get((typ, jvno), [])
        if not rows:
            continue
        expense_date = parse_date(h.get("Date")) or date.today()
        header_note = (h.get("Note") or "").strip()
        ref = (h.get("REF") or "").strip()

        expense_lines = [
            r
            for r in rows
            if str(r.get("DC") or "").upper() == "D"
            and any(str(r.get("ACCNO") or "").startswith(p) for p in EXPENSE_ACCOUNT_PREFIXES)
        ]
        ei = 0
        for row in expense_lines:
            amt = D(row.get("AMT"))
            if amt <= 0:
                continue
            acc_no = str(row.get("ACCNO") or "")
            cat = _category_for_expense(acc_no, expense_accounts)
            line_note = (row.get("Note") or header_note or "").strip()
            expenses.append(
                {
                    "legacy_type": typ,
                    "legacy_jvno": jvno,
                    "legacy_accno": acc_no,
                    "expense_no": _opex_expense_no(jvno, acc_no, ei),
                    "category_code": cat["code"],
                    "category_name": cat["name"],
                    "expense_date": expense_date.isoformat(),
                    "currency": "USD",
                    "amount": str(amt),
                    "exchange_rate": "1",
                    "description": line_note or cat["name"],
                    "reference": ref,
                    "status": "POSTED",
                }
            )
            ei += 1
    return expenses


def build_client_indexes(clients: list[dict], accounts: list[dict], idcards: list[dict]):
    by_legacy = {c["legacy_id"]: c for c in clients}
    by_acc = {}
    for row in idcards:
        if str(row.get("Type") or "").upper() != "C":
            continue
        legacy_id = str(row.get("IDNO") or "").strip()
        acc_no = (row.get("AccNo") or "").strip()
        client = by_legacy.get(legacy_id)
        if not client:
            continue
        if acc_no:
            by_acc[acc_no] = client
            by_acc[f"411{acc_no}"] = client
            by_acc[f"4110000{acc_no}"] = client
            by_acc[f"41100000{acc_no}"] = client
    for acc in accounts:
        acc_no = str(acc.get("AccNo") or "").strip()
        if not acc_no.startswith("411"):
            continue
        idno = str(acc.get("IDNO") or "").strip()
        if idno and idno in by_legacy:
            by_acc[acc_no] = by_legacy[idno]
    return by_legacy, by_acc


def write_jsonl(path: Path, rows: list[dict]):
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    data = load_source(args.csv_dir)

    clients = transform_clients(data["idcards"], data["accounts"])
    suppliers = transform_suppliers(data["accounts"], data["footers"])
    service_types = transform_service_types(data["footers"])
    clients_by_legacy, clients_by_acc = build_client_indexes(clients, data["accounts"], data["idcards"])
    suppliers_by_acc = {s["legacy_acc_no"]: s for s in suppliers}
    service_by_item = {st["legacy_item_code"]: st for st in service_types}

    expense_accounts = build_expense_accounts_index(data["accounts"])
    invoices = transform_invoices(
        data["headers"],
        data["footers"],
        clients_by_legacy,
        suppliers_by_acc,
        service_by_item,
    )
    payments = transform_payments(
        data["jheaders"], data["jdetails"], clients_by_acc, suppliers_by_acc, {}
    )
    operating_expenses = transform_operating_expenses(
        data["jheaders"], data["jdetails"], expense_accounts
    )
    supplier_journal_credits = transform_supplier_journal_credits(
        data["jheaders"],
        data["jdetails"],
        suppliers_by_acc,
        data["headers"],
    )

    manifest = {
        "extracted_at": datetime.now().isoformat(),
        "source": data["source"],
        "company": {
            "name": data.get("company", {}).get("CompanyName", "SAMA TOURS"),
            "legacy_code": data.get("company", {}).get("CompanyCODE", "SATO26"),
        },
        "counts": {
            "clients": len(clients),
            "suppliers": len(suppliers),
            "service_types": len(service_types),
            "invoices": len(invoices),
            "invoice_lines": sum(len(i["lines"]) for i in invoices),
            "payments": len(payments),
            "operating_expenses": len(operating_expenses),
            "expense_categories": len({e["category_code"] for e in operating_expenses}),
            "supplier_journal_credits": len(supplier_journal_credits),
            "unpaid_invoices_legacy": len(data.get("unpaid") or []),
        },
    }

    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_jsonl(args.output / "clients.jsonl", clients)
    write_jsonl(args.output / "suppliers.jsonl", suppliers)
    write_jsonl(args.output / "service_types.jsonl", service_types)
    write_jsonl(args.output / "invoices.jsonl", invoices)
    write_jsonl(args.output / "payments.jsonl", payments)
    write_jsonl(args.output / "operating_expenses.jsonl", operating_expenses)
    write_jsonl(args.output / "supplier_journal_credits.jsonl", supplier_journal_credits)

    print(json.dumps(manifest, indent=2))
    print(f"Staging written to {args.output}")


if __name__ == "__main__":
    main()
