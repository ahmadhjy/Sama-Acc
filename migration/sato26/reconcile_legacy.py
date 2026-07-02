"""Reconcile SATO26 legacy SQL data vs Sama imported data."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

# Django setup
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import django

django.setup()

import pyodbc
from django.db.models import Sum
from sales.models import SalesInvoice, SalesInvoiceLine
from treasury.models import Payment, ARAllocation
from accounts_core.models import Client

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost;DATABASE=SATO26_RESTORE;"
    "Trusted_Connection=yes;TrustServerCertificate=yes;Encrypt=yes;"
)
cur = conn.cursor()

print("=" * 60)
print("1. BACKUP / DATABASE INVENTORY")
print("=" * 60)

cur.execute("SELECT DB_NAME(), @@VERSION")
print("Database:", cur.fetchone()[0])

cur.execute("SELECT COUNT(*) FROM SalesHeader WHERE Type='SI'")
legacy_si_count = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM SalesFooter WHERE Type='SI'")
legacy_sf_count = cur.fetchone()[0]
cur.execute("SELECT MIN(Date), MAX(Date) FROM SalesHeader WHERE Type='SI'")
legacy_dates = cur.fetchone()
cur.execute("SELECT SUM(CAST(GrossTotal AS DECIMAL(18,2))) FROM SalesHeader WHERE Type='SI'")
legacy_si_total = cur.fetchone()[0]
cur.execute("SELECT SUM(CAST(AmountPaid AS DECIMAL(18,2))), SUM(CAST(AmountRest AS DECIMAL(18,2))) FROM SalesHeader WHERE Type='SI'")
legacy_paid, legacy_rest = cur.fetchone()

print(f"Legacy SalesHeader SI: {legacy_si_count} invoices")
print(f"Legacy SalesFooter SI: {legacy_sf_count} lines")
print(f"Legacy date range: {legacy_dates[0]} to {legacy_dates[1]}")
print(f"Legacy GrossTotal sum: {legacy_si_total}")
print(f"Legacy AmountPaid sum: {legacy_paid} | AmountRest sum: {legacy_rest}")

cur.execute("SELECT COUNT(*) FROM UnpaidInvoices")
print(f"Legacy UnpaidInvoices rows: {cur.fetchone()[0]}")

cur.execute("SELECT Type, COUNT(*) FROM JournalHeader GROUP BY Type ORDER BY Type")
print("Journal types:", cur.fetchall())

cur.execute("SELECT COUNT(*) FROM JournalHeader WHERE Type='RV'")
rv_count = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM JournalHeader WHERE Type='PV'")
pv_count = cur.fetchone()[0]
print(f"Legacy RV receipts: {rv_count}, PV payments: {pv_count}")

# Compare header total vs footer line sum
cur.execute(
    """
    SELECT h.InvNumber, h.GrossTotal,
           (SELECT SUM(CAST(f.Price AS DECIMAL(18,2))) FROM SalesFooter f
            WHERE f.Type='SI' AND f.InvNumber=h.InvNumber) AS line_sum
    FROM SalesHeader h WHERE h.Type='SI'
    """
)
mismatches = []
for inv, gross, line_sum in cur.fetchall():
    g = Decimal(str(gross or 0))
    ls = Decimal(str(line_sum or 0))
    if abs(g - ls) > Decimal("0.01"):
        mismatches.append((inv, g, ls, g - ls))
print(f"\nInvoices where header GrossTotal != sum(line Price): {len(mismatches)}")
for m in mismatches[:10]:
    print(f"  Inv {m[0]}: header={m[1]} lines={m[2]} diff={m[3]}")

print("\n" + "=" * 60)
print("2. SAMA IMPORTED DATA")
print("=" * 60)

sama_inv = SalesInvoice.objects.filter(invoice_no__startswith="SATO26-")
sama_count = sama_inv.count()
sama_lines = SalesInvoiceLine.objects.filter(invoice__in=sama_inv).count()
sama_grand = sama_inv.aggregate(t=Sum("grand_total"))["t"] or Decimal("0")
sama_dates = (sama_inv.order_by("issue_date").values_list("issue_date", flat=True).first(),
              sama_inv.order_by("-issue_date").values_list("issue_date", flat=True).first())
sama_payments_in = Payment.objects.filter(receipt_no__startswith="SATO26-RV-")
sama_payments_out = Payment.objects.filter(receipt_no__startswith="SATO26-PV-")

print(f"Sama SATO26 invoices: {sama_count}")
print(f"Sama SATO26 lines: {sama_lines}")
print(f"Sama date range: {sama_dates[0]} to {sama_dates[1]}")
print(f"Sama grand_total sum: {sama_grand}")
print(f"Sama RV payments: {sama_payments_in.count()}, PV: {sama_payments_out.count()}")
print(f"Sama RV amount sum: {sama_payments_in.aggregate(t=Sum('amount'))['t']}")
print(f"Sama PV amount sum: {sama_payments_out.aggregate(t=Sum('amount'))['t']}")

print("\n" + "=" * 60)
print("3. PER-INVOICE COMPARISON (legacy vs Sama)")
print("=" * 60)

cur.execute(
    """
    SELECT InvNumber, GrossTotal, AmountPaid, AmountRest, DBAccount, Date, JVNO
    FROM SalesHeader WHERE Type='SI' ORDER BY CAST(InvNumber AS INT)
    """
)
legacy_invoices = {str(r[0]): r for r in cur.fetchall()}

diffs = []
missing_in_sama = []
missing_in_legacy = []
for inv_no, row in legacy_invoices.items():
    sama_no = f"SATO26-SI-{inv_no.zfill(5)}"
    si = sama_inv.filter(invoice_no=sama_no).first()
    if not si:
        missing_in_sama.append(inv_no)
        continue
    legacy_gross = Decimal(str(row[1] or 0))
    sama_gross = si.grand_total or Decimal("0")
    if abs(legacy_gross - sama_gross) > Decimal("0.01"):
        diffs.append({
            "inv": inv_no,
            "legacy_gross": legacy_gross,
            "sama_gross": sama_gross,
            "diff": legacy_gross - sama_gross,
            "legacy_rest": row[3],
        })

for si in sama_inv:
    leg_num = si.invoice_no.replace("SATO26-SI-", "").lstrip("0") or "0"
    if leg_num not in legacy_invoices and si.invoice_no.startswith("SATO26-"):
        missing_in_legacy.append(si.invoice_no)

print(f"Missing in Sama: {len(missing_in_sama)} {missing_in_sama[:5]}")
print(f"Missing in legacy: {len(missing_in_legacy)}")
print(f"Amount mismatches (header GrossTotal vs Sama grand_total): {len(diffs)}")
for d in diffs[:15]:
    print(f"  Inv {d['inv']}: legacy={d['legacy_gross']} sama={d['sama_gross']} diff={d['diff']} legacy_rest={d['legacy_rest']}")

print("\n" + "=" * 60)
print("4. UNPAID INVOICES (legacy AR snapshot)")
print("=" * 60)

cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='UnpaidInvoices'")
u_cols = [r[0] for r in cur.fetchall()]
print("UnpaidInvoices columns:", u_cols)
cur.execute("SELECT TOP 20 * FROM UnpaidInvoices")
cols = [d[0] for d in cur.description]
for row in cur.fetchall():
    print(dict(zip(cols, row)))

print("\n" + "=" * 60)
print("5. CLIENT AR: legacy AmountRest vs Sama outstanding")
print("=" * 60)

# Legacy AR by client (DBAccount = IDNO)
cur.execute(
    """
    SELECT h.DBAccount, ic.AccName, SUM(CAST(h.AmountRest AS DECIMAL(18,2))) AS total_rest,
           COUNT(*) AS inv_count
    FROM SalesHeader h
    LEFT JOIN IDCard ic ON ic.IDNO = h.DBAccount
    WHERE h.Type='SI' AND CAST(h.AmountRest AS DECIMAL(18,2)) <> 0
    GROUP BY h.DBAccount, ic.AccName
    ORDER BY ABS(SUM(CAST(h.AmountRest AS DECIMAL(18,2))) DESC
    """
)
legacy_ar = cur.fetchall()
print(f"Legacy clients with non-zero AmountRest: {len(legacy_ar)}")
for row in legacy_ar[:15]:
    print(f"  IDNO={row[0]} {row[1]}: rest={row[2]} ({row[3]} inv)")

# Sama client outstanding
print("\nSama top client balances (grand_total - allocations):")
clients_with_inv = Client.objects.filter(sales_invoices__invoice_no__startswith="SATO26-").distinct()
sama_ar = []
for c in clients_with_inv:
    bal = c.outstanding_receivable
    if bal and abs(bal) > Decimal("0.01"):
        sama_ar.append((c.name_en, c.client_code, bal))
sama_ar.sort(key=lambda x: abs(x[2]), reverse=True)
for name, code, bal in sama_ar[:15]:
    print(f"  {code} {name}: {bal}")

print("\n" + "=" * 60)
print("6. RV PAYMENTS vs legacy receipts")
print("=" * 60)

cur.execute(
    """
    SELECT h.JVNO, h.Date, h.Note,
           (SELECT SUM(CAST(d.AMT AS DECIMAL(18,2))) FROM JournalDetail d
            WHERE d.Type='RV' AND d.JVNO=h.JVNO AND d.DC='C' AND d.ACCNO LIKE '411%') AS client_amt
    FROM JournalHeader h WHERE h.Type='RV' ORDER BY CAST(h.JVNO AS INT)
    """
)
legacy_rv = {str(r[0]): r for r in cur.fetchall()}
sama_rv_missing = []
sama_rv_amt_diff = []
for jvno, row in legacy_rv.items():
    receipt = f"SATO26-RV-{jvno.zfill(5)}"
    p = Payment.objects.filter(receipt_no=receipt).first()
    if not p:
        sama_rv_missing.append(jvno)
        continue
    leg_amt = Decimal(str(row[3] or 0))
    if abs(leg_amt - p.amount) > Decimal("0.01"):
        sama_rv_amt_diff.append((jvno, leg_amt, p.amount))

print(f"Legacy RV count: {len(legacy_rv)}")
print(f"Missing RV in Sama: {len(sama_rv_missing)} {sama_rv_missing[:10]}")
print(f"RV amount mismatches: {len(sama_rv_amt_diff)}")
for d in sama_rv_amt_diff[:10]:
    print(f"  JVNO {d[0]}: legacy={d[1]} sama={d[2]}")

print("\n" + "=" * 60)
print("7. STAGING JSON vs SQL (extract integrity)")
print("=" * 60)

staging = Path(__file__).resolve().parents[2] / "exports" / "sato26" / "staging" / "invoices.jsonl"
import json

staging_count = sum(1 for _ in staging.open(encoding="utf-8"))
print(f"Staging invoices.jsonl lines: {staging_count}")
print(f"SQL legacy SI count: {legacy_si_count}")
print(f"Match: {staging_count == legacy_si_count == sama_count}")

conn.close()
